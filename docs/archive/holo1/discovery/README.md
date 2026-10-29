# Cold format discovery (holo1)

Archived 2026-09-05 during the v1 receiver retirement (Phase 4.2 of the
`receiver-retirement` plan; ruling: `holo3/retirement_docs-2026-09/
GATE-E-BRIEF.md` §2 decision 4, accepted by Germano 2026-09-05). Not
deleted: this is a later-port candidate, not dead code. The measured
ground for the retirement as a whole is `HOLO1-BLAST-RADIUS.md`; the
capability-specific ground is `PORT-BRIEFS/cold-format-discovery.md`,
reproduced in full below.

## What it is and does

Cold format discovery is the v1 receiver's ability to identify which
registered printed format a set of scans holds, given only the scans —
no `--coding` and no `--format`. `docs/RECEIVE-DESIGN.md` §8 (quoted in
full in `RECEIVE-DESIGN-discovery-clauses.md` alongside this file)
states it as the default CLI entry:

> The default CLI entry is discovery-first. `format/registry.py` supplies
> the frozen complete-row domain. `discovery_state.py` persists only the
> discovery policy id, requested rows, cross-row placement-domain
> envelope, authenticated capture facts plus the native E021 `c`
> decision, and isolated exact-row `SessionState` branches; candidate ids
> come from those branches, and per-candidate completion, c-based
> exclusion, the selected row, root status, and decoder count are
> derived directly — no parallel prune, trial, or selection ledger.

Mechanically: `discovery.py`'s module docstring calls it "discovery-first,
receiver-wide orchestration over exact-row branches" — one ordinary
exact-row receive session per candidate format row, run under a single
shared cross-row placement-domain envelope (`PlacementDomainEnvelope`,
so every branch prices the same page-hypothesis domain identically), with
two narrowing mechanisms and one terminal rule layered on top:

- **E021 `c` exclusion.** Each capture's native cell-dots decision (`c`,
  e.g. 2 or 3) is decided once per capture and used only to exclude
  format rows of an incompatible cell family — never duplicated as a
  per-branch survey product (each branch still runs its own full
  E022→E023 pipeline unchanged).
- **The conflict terminal.** Exactly one candidate row may ever produce a
  CRC-certified tile. A certificate from a second row is a terminal,
  integrity-fatal format conflict (`DiscoveryStatus.INTEGRITY_FAILURE`),
  not a tie-break — "the first row that certifies wins" was explicitly
  rejected in the port brief as a weaker, less safe receiver than
  "exactly one row may certify."
- **Root verification** waits until every (candidate row, capture) pair
  in the current round is derivably complete or `c`-excluded before it
  will call a row selected; a deliberately interrupted, partially active
  branch is never mistaken for a complete one.

The root exposes the receiver-wide count of all actual CRC decoder
invocations (`DiscoveryState.decoder_invocations`) and, once the round is
complete, the uniquely selected row id, if any
(`DiscoveryState.selected_row_id`) and a `DiscoveryStatus` (`OPEN`,
`VERIFIED`, `INTEGRITY_FAILURE`, or `UNSUPPORTED`).

## Entry points

The CLI's `holo decode` fires discovery automatically whenever the
operator supplies neither `--coding` nor `--format` and any existing
state file is not already an exact-row session — the predicate, in
`cmd_decode` (`src/holo/cli.py:442-444` at f006abc):

```python
discovery_mode = (
    args.coding is None and args.format_ref is None
    and established_magic != STATE_MAGIC)
```

Two code spans build and invoke the discovery request; both are quoted
verbatim in `cli-discovery-branch.py.txt` in this directory, with their
own header:

- **`src/holo/cli.py:455-478`** — builds the `DiscoveryReceiveRequest`
  (optional `--printer` narrowing to `DEFAULT_DISCOVERY_ROW_IDS`, then
  the request itself: captures, state path, candidate row ids, page
  hypotheses, and the `--complete`/`--mopup`/`--refine` flags).
- **`src/holo/cli.py:632-637`** — the call to `run_discovery_receive`
  inside the warnings-filter block shared with the exact-row path.

(`PORT-BRIEFS/cold-format-discovery.md`, reproduced below, cites this
entry point as `cli.py:456-473`; the line numbers above are verified
against this archive's own commit, f006abc, and are the ones to trust —
`cli.py` had moved slightly since the brief was drafted.)

Both spans, along with the `discovery_mode` predicate and the
discovery-only result printing later in `cmd_decode` (`cli.py:702-712`),
are deleted in the same phase that installs the
`confetti.py decode` forwarder (Phase 4.1) — the forwarder refuses the
no-`--coding`/no-`--format` case outright rather than routing to
discovery.

The library entry point (independent of the CLI) is
`run_discovery_receive(request, *, observer_factory=None)` in
`discovery.py:420-425`, taking a `DiscoveryReceiveRequest`
(`discovery.py:59-99`: captures, optional state path, optional
`candidate_row_ids`/`page_hypotheses`, the deferred-close/mopup/refine
flags) and returning a `DiscoveryReceiveResult`
(`discovery.py:101-121`: the `DiscoveryState`, whether it changed,
optional recovered payload bytes, qualification status/notes, and any
observer failures).

## The state file (`discovery_state.py`)

`discovery_state.py` (395 lines) defines the durable root a discovery
run persists to disk — a single JSON-typed state file distinct from an
exact-row session file (different magic: `DISCOVERY_MAGIC =
"holo-receive-discovery"`, schema version 12 at this sha, with
migrations from schema 11 in `DISCOVERY_MIGRATIONS`). Its module
docstring states the design choice directly:

> The exact-row receiver deliberately keeps format-specific evidence in a
> single namespace. Discovery therefore owns one root state containing
> isolated exact-row branches instead of adding a format dimension to
> every pose, observation, certificate, and close record.

`DiscoveryState` (`discovery_state.py:71-199`) holds:

- `discovery_policy_id` — a policy hash binding the candidate domain,
  the shared placement envelope, and every branch's own policy id
  (`discovery.py:_policy_id`, `discovery.py:178-198`);
- `requested_row_ids` — the full row set the operator asked for (before
  any exclusion);
- `domain_envelope` — the shared `PlacementDomainEnvelope` every branch
  prices against;
- `branches` — one ordinary exact-row `SessionState` per surviving
  candidate row, canonically sorted by format row id;
- `surveys` — one `DiscoverySurvey` per capture (`facts` +
  the native E021 `c_dots` decision, or `None` before that capture has
  been surveyed).

Derived, not stored: `candidate_row_ids`, `candidate_complete`,
`round_complete`, `selected_row_id`, `status`, and
`decoder_invocations` are all properties/methods computed from the
branches and surveys above — never a parallel ledger. `validate_discovery`
(`discovery_state.py:201-252`) checks every branch's own session
invariants plus discovery-specific ones (canonical page domains, every
capture's facts matching its root survey, no branch retaining a capture
its own native `c` should have excluded). `save_discovery`/
`load_discovery`/`*_with_digest` (`discovery_state.py:255-366`) are the
atomic-write, authenticated-hash persistence pair, mirroring the exact-row
session's own `state_codec.py` machinery. `state_file_magic`
(`discovery_state.py:369-370`) is what `cmd_decode` reads to tell a
discovery state file from an exact-row one before deciding how to resume.

## The tests that pinned it

Four test files exercised discovery behavior at this sha; three move with
this archive move, the fourth (a single test in an otherwise
receiver-general module) is preserved as a snippet per the Gate E ruling
rather than relocating its whole file:

- **`tests/holo/test_receive_discovery.py`** (974 lines; moved here by the
  lead's `git mv`) — "Receiver-wide format discovery, state, and CLI
  routing." Covers registered-row completeness, the deferred-close bool
  guard, the shared placement-domain envelope (including its refusal of
  foreign/undercovered domains), empty-state round-trips, deferred/
  terminal/conflict resume behavior, certificate recognition and the
  conflict terminal, `c`-based exclusion, the one-final-close rule, and
  the CLI routing tests (`test_cli_decode_defaults_to_discovery`,
  `test_cli_complete_reaches_discovery_request`,
  `test_cli_printer_hint_does_not_promote_catalog_only_color_rows`,
  `test_cli_without_coding_resumes_an_exact_registered_state`,
  `test_cli_refuses_exact_hint_for_discovery_state`).
- **`tests/holo/test_receive_discovery_integrity.py`** (675 lines; moved
  here by the lead's `git mv`) — "Discovery persistence, resume, and
  observer-integrity regressions." Covers level-outcome derivation,
  capture-authority rejection of invalid facts, flat-decision persistence
  and resume, rejection of format-derived branch corruption, terminal
  observer bootstrapping, the terminal-conflict-stops-open-children rule,
  fact reauthentication without re-running E021, byte-different
  acquisitions as distinct captures, page-filtered candidate-set resume,
  the no-retry-choice invariant, exposed observer failures, sha-pinned
  child diagnostic lineage, scale-local `c` mismatch refusal, the
  nested-stop-after-one-barrier rule, active-capture resume ordering, and
  rejection of a forged terminal branch.
- **`tests/holo/test_receive_bch_quarantine.py`** (589 lines; stays in
  place, receiver-only, deleted with the rest of the v1 suite in
  Phase 4) — its one discovery case,
  `test_discovery_load_rejects_derived_bch_nonconflict` (with its two
  helpers `_state_with_conflict` and `_durable_pose`), is preserved
  verbatim in `quarantine-discovery-test.py.txt` in this directory. It
  pins that a lean (derived, non-conflicting) BCH conflict record is
  rejected on discovery load unless it is rebound to match the row's own
  format.
- **`tests/holo/test_receive_policy_detach.py`** exercises discovery
  detach paths too, but GATE-E-BRIEF.md decision 4 rules it
  receiver-only and it is deleted outright, not archived.

## Port brief

Reproduced in full from `holo3/retirement_docs-2026-09/PORT-BRIEFS/
cold-format-discovery.md` (that file remains the source of record; this
copy is for a reader who only has this archive directory open).

---

> PORT BRIEF — cold format discovery (holo1 discovery.py + discovery_state.py).
> WHAT IT DOES. Given only captures, finds which registered printed format a sheet is, by running one isolated decode branch per candidate row and requiring exactly one to certify.
> INPUTS. Scan paths with declared dpi; optionally a --printer narrowing; the registry's row domain. OUTPUTS. A selected row id (or a refusal), the per-branch session states, a decoder-invocation census, and a durable root that can be resumed.
> WHERE THE CODE LIVES TODAY. src/holo/receive/discovery.py (860 lines: DiscoveryReceiveRequest :59-99, _candidate_layout :147-175, _new_state :221-252, run_discovery_receive :420) and src/holo/receive/discovery_state.py (395 lines: schema 12 and its migrations :36-47, survey and exclusion :57-67 / :148-164, selection and the conflict terminal :178-196, round completion :166-176, validation :201-254, digest and IO :255-366).
> Entry point src/holo/cli.py:456-473. Tests: the discovery lanes under tests/holo; freeze their names in PRESERVATION before deletion.
> WHAT IT WOULD ATTACH TO IN HOLO3. (1) Candidate enumeration — holo3/format/identity.py already totals over L:/legacy/catalog/v2 refs and holds the fourteen fossils, so the row domain is a missing FUNCTION, not missing data.
> (2) Per-candidate isolation — holo3's engine builds one store bound to one FormatRow, so a port is N engine runs plus a selection wrapper, not a format dimension inside the store. (3) The shared hypothesis envelope — holo3 prices the page domain per format row (docs/PAGE-DOMAIN.md §5), so a cross-row envelope is the one genuinely new object. (4) The entry point — holo3/cli.py:56-58 is where 'format identity required' is raised today.
> WHAT MUST NOT BE SIMPLIFIED. 'The first row that certifies wins' is a weaker and less safe receiver than 'exactly one row may certify' (row 17). Carry the conflict terminal, the round-completion rule and the decoder census.
> ORDER. Build it after rows 16-18, which are its parts: the exclusion narrows the list, the terminal decides the answer, the root makes it resumable.
> WHAT EVIDENCE WOULD SHOW IT PAID. There is none today (ARTEFACTS.md G-14). The port should be gated on a measured number it can generate cheaply: on one archived capture whose row is known, the cost of a discovery-first entry against the told entry, and the number of candidates the cell-family vote excludes before any address word is decoded. Both are minutes on holo3's sim lanes.
> SIZE. 1,255 lines across two modules, plus the CLI branch; no production dependency outside src/holo/receive, so it lifts cleanly.
> COST SHAPE. Roughly N times the survey and cold-placement cost, minus whatever the cell vote excludes; the branches share nothing but the envelope. Discovery states stay outside any resume-forgiveness rule — they are short-lived identification artefacts, not archives.

---

## Provenance and how to run the archived code

Files in this directory:

| file | what it holds |
|---|---|
| `discovery.py` | the orchestrator (`git mv` from `src/holo/receive/discovery.py`) |
| `discovery_state.py` | the durable root (`git mv` from `src/holo/receive/discovery_state.py`) |
| `test_receive_discovery.py` | discovery + CLI-routing tests (`git mv` from `tests/holo/`) |
| `test_receive_discovery_integrity.py` | persistence/resume/integrity tests (`git mv` from `tests/holo/`) |
| `README.md` | this file |
| `cli-discovery-branch.py.txt` | `cli.py`'s discovery request-construction and invocation lines, verbatim |
| `quarantine-discovery-test.py.txt` | the one discovery test from `test_receive_bch_quarantine.py`, verbatim, with its helpers |
| `RECEIVE-DESIGN-discovery-clauses.md` | `docs/RECEIVE-DESIGN.md` §8's discovery clauses, verbatim, with line numbers |

The four `git mv`'d files (above) were moved, unedited, by the commit that
moved these files (the lead's next commit on `receiver-retirement` after
this material was prepared) — every blob is therefore byte-identical to
its pre-move blob at f006abc, and `git log --follow <file>` reaches the
full history through the move. This mirrors how holo2's archive was
handled: those 31 files moved at a single sha (`39df5cf`) with nothing
edited in the same commit.

None of `discovery.py`/`discovery_state.py`'s imports (`holo.format.*`,
`.observer`, `.place`, `.placement.policy`, `.production`, `.runtime`,
`.scan`, `.session`, `.survey`, `.types`) travel with them into this
archive — they stay in `src/holo/receive`, which Phase 4 deletes as a
whole. The two modules and their tests are therefore **not importable
from this directory as archived**; they document a capability and its
proof, not a standalone library. To actually run the archived code
(re-decode an old capture, re-run the discovery test suite, or read one
of the frozen `.state`/discovery-state files that predate the deletion),
check out the whole pre-deletion tree in a worktree at the tag the Gate D
ruling puts on `main` before the merge:

```sh
git worktree add ../paper-v1 pre-v1-v2-deletion
cd ../paper-v1
env/bin/python -m pytest tests/holo/test_receive_discovery.py \
    tests/holo/test_receive_discovery_integrity.py -q
./confetti.py decode --scan-dpi <dpi> <scan> --state <path>
```

(At that tag `./confetti.py` is still the v1 wrapper around `holo.cli`,
before the Phase 4.1 forwarder retargets it to `holo3.cli` — it resolves
its `env/` relative to the CWD, so run it from the worktree root.)

At the time this archive material was prepared, `pre-v1-v2-deletion` did
not yet exist — GATE-E-BRIEF.md §3 step 8 places its creation at the
Phase 4 merge, on `main`, after every other gate passes. `docs/archive/
holo1/README.md` (the top-level holo1 archive index, not this
subdirectory) carries the same recipe for the rest of the receiver.
