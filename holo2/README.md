# holo2 — receiver restart: tile-map authority, dataflow workers

Status (2026-08-22): **H0–H5 EXIT MET, plus the FORMAT-SPACE/`--no-close`/
pyflakes catch-up wave LANDED** (`holo2/docs/CATCHUP-PLAN.md`) — holo2 now
NAMES a printed sheet the way `src/holo` does: one `--format <id>` flag
takes a v2 identity or an `L:<legacy-spec-id>` fossil line (twelve of
`src/holo`'s fourteen catalogued identities, byte-matched, incl. both
hardware-certified K volumes), the full v2 grammar (families k/cmy7/cmy8,
every registered pitch class and lawful rational, every `LADDER` rung),
and colour rows are nameable and buildable — their CODECS still fail
FATALLY, since no colour receive code landed this wave. `--no-close`
skips the close journal line on ingestion/replay (a read-time fold
policy, never a rewrite). The design is federated per package. Bare
`pytest` is the fast suite and nothing else (`holo2/tests` +
`tests/holo2_oracles`, the carry-oracle tripwires, 2701 passed / 0
skipped); the verdicts gate (`holo2/measure/verdicts/`) is nine verdicts
/ 40 checks over five shared real decodes plus one CLI-driven end-to-end
run (~91 s), run at wave end and (round-trip only) at package
hand-off/pre-merge. Nothing here is qualified; the receiver status of
anything built from this tree is PROVISIONAL until a recorded
qualification says otherwise (DESIGN L15), and the design itself
becomes normative only by user declaration.

holo2 is a receiver-only restart. It decodes the **unchanged printed
format v1** (generation, format anchors, goldens, and the characterize
instrument all stay in `src/holo`); what it replaces is the receiver's
control plane — lanes-and-rungs scheduling becomes a dataflow of window
and tile workers over a tile-map authority with per-capture done-pixel
projection.

- `holo2/docs/DESIGN.md` — **the constitution**: vision, the two truth
  planes, the laws, the glossary, the cross-cutting contracts, pointers.
- `holo2/src/holo2/<package>/DESIGN.md` — the subsystem contracts. Each
  package carries its own purpose, public surface, owned record
  families, the laws it enforces, the measured facts it relies on, its
  open rulings, and its **TO-FIX ledger** (known defects, one line
  each). Subsystem decisions land there, not in the root doc, whose §15
  is the ledger for what crosses packages.
- `holo2/docs/ENGINEERING.md` — how work lands here (firewall, layering,
  receiver-path invariants, review bars).
- `holo2/docs/CAPABILITIES.md` — designed / implemented / verified /
  deferred, one row per capability.
- `holo2/docs/WORKPLAN.md` — build order, gates, and what is owed next.
- `holo2/docs/MEASUREMENTS.md` — the recorded numbers (living), reading
  `holo2/docs/measurements-h3.json` (the raw record), plus the HEALTH
  ledger.
- `holo2/docs/H3BIS-ARCHITECTURE-REVIEW.md` — the adversarial review;
  its findings are mapped to owning packages in `WORKPLAN.md` §H3.5.
- `holo2/src` — the pythonpath root; the package itself is
  `holo2/src/holo2/` (importable as `holo2`).
- `holo2/tests/` — internal tests (import `holo2` only): a measurement
  reads clocks and the receiver may not (DESIGN L12), so measuring
  happens outside the library, in `holo2/measure/` — never through a
  generic test run.

## Firewall

`holo2/src` imports **nothing** from `src/holo`, `src/paperholo`, or
`experiments/` — same rule as the paperholo/holo boundary. Production
pieces are **copied and adapted, never imported**; divergence from
`src/holo` is deliberate (holo stays the reader of record for already-
printed material until holo2 is qualified). Equivalence where intended is
pinned by comparison tests **outside** this tree (`tests/holo2_oracles/` at
repo root), which may import both packages (qualification-only oracles).
