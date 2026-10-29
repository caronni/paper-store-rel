# Receiver retirement record — 2026-09

The record of the campaign that maps holo2 and holo1 (`src/holo/receive`)
into holo3, carries judicious comments and constant provenance into holo3,
archives what must be saved, and then deletes `holo2/` and replaces
`src/holo/receive` with holo3. Plan of record: `claude-plan.md` at the
repo root (Germano's copy; gates A–E are its control surface).

## Gate log

| gate | decision | date |
|---|---|---|
| A — plan approved | passed | 2026-09-02 |
| B — divergences ruled | 2026-09-03: en-bloc acceptance given provisionally ("if we won't lose anything yield-bearing"); D1 accept + loud warning · D2 document · D3 provisional (port behind a dial, A/B first) · D4 yes · D5 port · D6 = (a) keep, local standing context recorded as an open toolbox line (2026-09-04); blocks 2–7 stand as recorded; full 129 in `RULINGS-full.md`. **PASSED** | 2026-09-04 |
| C — comment carry approved | **PASSED 2026-09-04 per the lead's recommendation: Tier A + Tier B (401 items) land; Tier C does not.** Charter amendment lands with it. | 2026-09-04 |
| D — holo2 deletion go | **PASSED 2026-09-05** (Germano): go; archive cut = the 31-file list; snapshot write and `verify/` scripts left as they are; merge only when the branch's work is done, main tagged `pre-v1-v2-deletion` first. Executed and CLOSED 2026-09-05: archive `39df5cf`, deletion `a805888`, docs + refuter fixes `23c64e5`; lanes green after (DELETION-LOG "Phase 3"). Next: Gate E brief. | 2026-09-05 |
| E — v1 receiver retirement go | Brief ready: `GATE-E-BRIEF.md` (ten decisions, the Phase 4 sequence) on the census `HOLO1-BLAST-RADIUS.md` (152 importers, 902 tests in 80 files, the ten state-reading instruments). **PASSED 2026-09-05** (Germano): go as proposed; `src/holo/receiver/docs/conversion_docs/verify/` DELETED rather than kept; mypy stays — a mypy/pyflakes hygiene gate is a line to open (measured, numbers in DELETION-LOG). **Phase 4 EXECUTED 2026-09-05**: forwarder + re-homes `b167b9f`, deletion `284ae3e`, trims + docs `a4a0ea5`, two laws re-homed `0873769`; final lanes and the close in DELETION-LOG "Phase 4". Merge = Germano: tag main `pre-v1-v2-deletion`, fast-forward. | 2026-09-05 |

## Files

| file | content |
|---|---|
| `ARTEFACTS.md` | inventory of existing measurement writeups and run artefacts, per volume and mechanism — the source of every number in the maps |
| `HOLO2-MAP.md` | one row per holo2 mechanism: classification, holo3 counterpart, implementation delta, equivalence evidence, both sides' numbers |
| `HOLO1-MAP.md` | the same for holo1, plus the "capabilities that leave with the tree" table |
| `RULINGS.md` | every DIVERGED / ABSENT / UNPROVEN row in plain words, options, recommendation, Germano's ruling inline |
| `PORT-BRIEFS/` | one brief per capability archived for later re-implementation in holo3 |
| `COMMENT-CARRY.md` | every candidate comment and constant provenance with verdict, rewritten text and holo3 anchor |
| `PRESERVATION.md` | what is saved where; what stays in git history only |
| `DELETION-LOG.md` | executed deletions with shas, test-count arithmetic, gate outputs |
| `GATE-E-BRIEF.md`, `HOLO1-BLAST-RADIUS.md` | the Gate E decision sheet and the v1-receiver blast-radius census it rests on (supersedes claude-plan.md Appendix D) |
| `GATE-D-BRIEF.md`, `HOLO2-ARCHIVE-CENSUS.md` | the Gate D decision sheet (archive index, deletion checklist, Phase 3 sequence) and the per-file census it rests on |
| `landing-set.json`, `tools/comment_only_diff.py` | the 401 Gate-C items keyed by module, and the AST gate every comment landing passed |
| `holo1-certificates/` | per archived holo1 state: certificate addresses per stream, close record, policy id |
| `seeds/` | the session's read-only inventories of the three trees and the deletion blast radius — ROW LISTS AND CONTEXT, NEVER VERDICTS |

## Vocabulary (one classification per row)

- **CARRIED-IDENTICAL** — bit-exact carry, pinned by an oracle test, a golden, or a recorded bit-exact verification.
- **CARRIED-DIFFERENT** — same intent, different implementation. Always carries the implementation delta and an equivalence-evidence status: PINNED / MEASURED (an existing artefact shows equal-or-better yield) / UNPROVEN (with the artefact or costed run that would settle it).
- **DIVERGED** — behaviour differs in a way that touches yield or core behaviour; both sides' measured record; needs a ruling.
- **ABSENT** — not in holo3; yield relevance from evidence; ruling: port now / archive for later port / accept the loss.
- **HOLO3-ONLY** — new in holo3; listed, no action.
- **OUT-OF-FILTER** — self-test, safeguards, journal/replay/leases, validation, diag rendering; one appendix line, never analysed.

Filter rule: a row enters a map if it changes which work runs, in what
order, or what gets certified.

## Principles that bind every row

1. Judge the thing that is: every verdict is re-derived from the current
   code on both sides. Past rulings, the holo3 build contract's
   "adopted"/"not built" lists, catalogue verdicts, grok's tables, the
   seeds here, and code comments supply row lists and context only. A
   feature deferred to contain complexity is a candidate, not a rejection.
2. A different implementation is a potential yield gap; it is investigated,
   not ticked off.
3. No receiver runs. Numbers come from `ARTEFACTS.md`. A run that is
   genuinely needed is a costed proposal in `RULINGS.md`.
4. Yield before pricing.
5. Rulings in plain words.

Pointer-target rule (binds the comment phase): a pointer comment names
`docs/archive/holo2/<file> §n`, `docs/archive/holo1/…`,
`docs/RECEIVE-DESIGN.md §n`, `src/holo/receiver/docs/conversion_docs/<spec>:line`, an
experiment log, or `<retirement-sha>:<path>:<line>` — never a live path a
later phase deletes.
