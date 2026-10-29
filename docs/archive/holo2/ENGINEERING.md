# ENGINEERING.md — how work lands in holo2

The durable SWE rules for this tree, human or agent. Briefs point here
instead of restating them. Design lives in `docs/DESIGN.md` (the
constitution) and in each package's own `DESIGN.md` (the subsystem
contracts, R4); this file is about *how* to work, not *what* to build.

## The firewall

- `holo2/src` imports **nothing** from `src/holo`, `src/paperholo`, or
  `experiments/`. Production pieces are **copied and adapted, never
  imported** (`holo2/README.md`).
- A carry is a copy with a declared adaptation: every executable line is
  the original unless `tests/holo2_oracles/test_oracle_carry_source.py` says
  otherwise. Changing a carried numeric path is a declared adaptation,
  never a silent edit.
- Equivalence with `src/holo` is pinned by oracles **outside** the tree
  (`tests/holo2_oracles/`), which may import both packages.

## Layering

- Packages: `core` (facts, store, commit, work protocol), `format`
  (printed truth), `capture` (pixels), `solve` (algorithms), `engine`
  (scheduling), `diag` (observer), `cli.py` (composition root).
- The DAG and its exceptions are DATA in
  `holo2/tests/test_layering.py`. Exceptions carry a burn-down phase and
  may only ever shrink. Adding one is a reviewable diff with a reason.
- Cross-package imports go through the target package's `__init__`
  surface (`__all__`), pinned in `holo2/tests/test_surfaces.py`.
  Underscore modules are package-private. **A surface advertises what
  the tree consumes** (B4): a name joins an `__all__` in the same diff
  as the first cross-package import of it — exception types included —
  and a name nobody imports from outside its package comes off. It stays
  importable from its own module, which is where its own tests name it.
- No cross-package globals. Module caches stay package-private;
  composition happens in `cli.py`. Nobody assigns to another holo2
  module's attributes.
- Tests mirror the package tree and obey the same DAG. Any test may
  attach `diag` and drive `cli`.
- Each package carries `src/holo2/<package>/DESIGN.md`: purpose, public
  surface, owned record families, the laws it enforces, the measured
  facts it relies on, its open rulings, and its **TO-FIX ledger**. A
  subsystem ruling lands there; a defect lands in that ledger (one line,
  a pointer, a severity) rather than in prose. The root doc gets an
  entry only when the item crosses packages or owns no package — that is
  `docs/DESIGN.md` §15.

## Receiver-path invariants (enforced by `test_conventions.py`)

- **No clocks.** Nothing under `holo2/src` reads a clock. Measurement is
  bench-side or observer-side, always outside the library.
- **No RNG.** Library code draws no random numbers. Determinism is the
  product: same inputs, same certificates, same order.
- **Deterministic iteration everywhere.** Sort, or use an order the data
  defines. No set iteration, no dict order that depends on insertion by
  a concurrent path, no `id()`-derived ordering.
- **≤1000 lines per file.** A file that outgrows the cap is a design
  signal; split along a seam, not at a line count.
- **Declared dependencies only** — numpy, scipy, Pillow, tifffile,
  cryptography. A new third-party import needs a user ruling, not a
  test edit.

## Freshness doctrine

Nothing here is final and nothing is owed backwards compatibility.

- No shims, no compatibility layers, no dead code, no "legacy" branches.
- Pre-freeze schema rule: a breaking change refuses old states loudly.
  No migration decoders.
- Re-encoding durable data is permitted as a deliberate, bigger step —
  say so, do it once, and re-earn the gate that proves it.
- Delete transient scaffolding when its phase ends (the R0 move proof is
  marked for deletion in its own docstring).

## Docstrings and comments

- A docstring states the **contract**: what the thing owns, what it
  refuses, what invariant it carries. Not a narration of the code, not a
  changelog, not an apology.
- Where the design is silent and the code had to choose, say so in the
  module docstring under "choices where DESIGN is silent" so the choice
  can be adjudicated instead of discovered.
- Numbers in comments are measured or derived, and say which. A budget
  records the measurement it came from.

## Moves and carries: the AST proof

Any phase that relocates or copies code proves it changed nothing:

1. Parse both sides, strip docstrings and every import, `ast.dump`.
2. Compare definition by definition; declare every difference in a
   table (`ADAPTATIONS`, `MOVES`) with its reason.
3. Reference the source by a pinned commit (`git show <sha>:<path>`),
   never `HEAD` — the proof must survive its own commit.

`tests/holo2_oracles/test_oracle_carry_source.py` is the standing worked example
(carry). The move example was `holo2/tests/test_move_proof_r0.py`, which
R0 marked transient and R1 deleted the moment it edited the moved
modules — read it at commit `2da9017` when you need the pattern.

## Health sentinels

- Pins for invariants, ledger rows for trends, alerts only where noise
  is characterized. Wall budgets ~3x measured, RSS budgets ~2x measured,
  both on the synthetic spine.
- All measurement in benches or observers, never in receiver paths.
- Profiling doctrine: never profile through a generic pytest run; use a
  small instrumented harness.
- Coverage is reported per package, not gated globally, and only after a
  baseline exists.

## Working rules for agents

- **Agents never commit.** Leave the tree dirty and report; the
  coordinator reviews and commits.
- **Flag ambiguity, do not resolve it silently.** If a brief is
  under-determined, pick the least-surprising option, do the work, and
  say in the report exactly what was ambiguous and what was chosen.
- **Stay in the lane.** A phase closes at its own finish line. Work that
  belongs to a later phase gets named in the report, not done.
- Do not touch `scratch/` (read-only archive) or another tree's sources.
- Physical actions (print/scan) are user-gated and out of scope here.

## Report format

Every round reports, in this order:

1. what changed — files and line counts, old→new for moves;
2. choices made where the brief was silent, with the reason;
3. deviations from the brief, and anything that could not be done
   cleanly, with why;
4. new pins/tests and the measured baselines behind them;
5. the pytest summary line, verbatim, for the exact command run.

## Review bars

A change is reviewed against the code, not the report:

- run the suite independently (`env/bin/python -m pytest holo2/tests
  tests/holo2_oracles -q`); a green claim without an independent run is not a
  green suite;
- spot-read the law-sensitive parts: layering-test diffs, public
  surfaces, moved-code proofs, anything touching commit/identity/close;
- reproduce a review's load-bearing finding against the real tree before
  accepting or rejecting it — reviews go stale when the tree moves under
  them;
- a should-pass control that fails the gate is a broken gate, not bad
  data.
