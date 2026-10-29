# holo1 archive — the retired v1 receiver

This directory holds what survives, in the tree, of `src/holo/receive` (the
v1 receiver) after its 2026-09-05 retirement. Everything else about v1 is
deleted (recoverable by sha, see below) or lives unmoved in `docs/` and
`holo3/retirement_docs-2026-09/`.

## What this archive holds

- **`discovery/`** — cold format discovery: `discovery.py` and
  `discovery_state.py` (the orchestrator and its durable root, `git mv`'d
  here unedited), their two test modules, one discovery test snippeted out
  of a third (receiver-general) module, a verbatim copy of `docs/
  RECEIVE-DESIGN.md` §8's discovery clauses, and a README. This is the one
  v1 capability archived whole, not just described — Gate E ruled it a
  later-port candidate, not dead code, since `holo3/format/identity.py`
  already supplies the row domain a port would enumerate. Read
  `discovery/README.md` for what it is and how it worked; it is not
  importable from here as archived (its imports stay in `src/holo/receive`,
  which Phase 4 deleted whole) — the state-reader recipe below runs it.

## What the v1 receiver was

The v1 receiver (`src/holo/receive`) was the E021→E023c composition —
survey, placement/addressing, ownership/calibration/LDPC, scale-barrier
certified refinement — that carried holo's production read-back from 2026-07
until holo3 superseded it. It is the only tree that ever closed a colour
volume: e032's first CMY8 close on the Xerox AltaLink (718,413 B,
2026-08-05/06) and the whole colour-uplift corpus (zero wrong certificates
in 69,066,304 audited cells) ran on it, and no later tree repeated either
result before this retirement. It was retired 2026-09-05 at `284ae3e`, once
holo3 matched and then passed it on every measured comparison in the Gate
B/C/D/E record.

## Where its design and record live

- `docs/RECEIVE-DESIGN.md` — the normative v1 design; historical from
  `284ae3e`, carrying its own retirement header and pointers to the living
  receiver docs (`holo3/API.md`, `SCHEDULE.md`, `docs/DIAG-DESIGN.md`,
  `docs/PAGE-DOMAIN.md`).
- `docs/COLOR-UPLIFT-{PLAN,MEASUREMENTS,REVIEW}.md` — the colour-uplift
  campaign's design, measurements, and external review.
- `docs/PLANE-FIELDS.md` — the per-plane registration-field line (never
  merged; V0 through W6 measured on this receiver).
- `holo3/retirement_docs-2026-09/HOLO1-MAP.md` — 225 rows mapping every v1
  mechanism to its holo3 counterpart (or absence), classified and ruled.
- `holo3/retirement_docs-2026-09/RULINGS.md` — the Gate B decision sheet:
  six decided questions plus the disposition of the other 123 entries.
- `holo3/retirement_docs-2026-09/PORT-BRIEFS/` — twelve capabilities Gate B
  recommended archiving for a later port rather than losing outright, one
  line each from their own first paragraph:
  - `cell-family-exclusion.md` — removes format-row candidates the printed
    cell size rules out, before any decoding.
  - `certificate-divergence-canary.md` — counts disagreements between every
    observed cell and every certificate at that address; non-gating, the
    source of "zero wrong certificates in N cells."
  - `cold-format-discovery.md` — finds which registered format a sheet is
    from captures alone (archived whole in `discovery/`, not just briefed).
  - `context-corrected-adoption-gate.md` — scores the refinement adoption
    gate with the same detector the decoder will actually read with.
  - `d16-surplus-audit.md` — re-encodes a solved fountain block's certified
    symbols from its solved sources, catching a wrong symbol an ordinary
    solve would silently mask.
  - `durable-discovery-root.md` — holds one discovery round on disk so it
    resumes and validates rather than restarting.
  - `refinement-evidence-namespacing.md` — lets a refined re-read coexist
    with its base read; only certificates cross between reads.
  - `refinement-lineage.md` — records which certificates a refined pose was
    fitted from and which certificates that refinement then enabled.
  - `row-selection-format-conflict.md` — turns finished candidate branches
    into one answer, refusing loudly if more than one explains the sheet.
  - `source-re-authentication.md` — confirms a scan file is still the file
    it hashed at ingest before any durable write attests to it.
  - `supplemental-baseline-arm.md` — one more read through the pre-campaign
    colour path, for tiles stranded by a configuration change.
  - `two-loser-ledger.md` — keeps a failed window's best near-miss as
    continuation geometry for a later window over the same paper.

## The state-reader recipe (Gate E decision 2)

The 28 archived v1 `.state` files from real print-day runs (e028 through
the colour-uplift campaign) are readable only by the retired receiver;
their frozen certificate sets, sizes and provenance are already recorded in
`holo3/retirement_docs-2026-09/holo1-certificates/INDEX.md`, so most
questions about them don't need a reader at all. When one does, the reader
is a worktree at the tag `pre-v1-v2-deletion` — Germano creates this tag on
`main` at the merge; it does not exist yet, and in the meantime `b167b9f`
is the last commit with the receiver still in the tree
(`git show b167b9f:src/holo/receive/<file>` reaches any of its modules):

```sh
git worktree add ../paper-v1 pre-v1-v2-deletion
cd ../paper-v1
ln -s <this repo>/env env
PYTHONPATH=src env/bin/python -m holo.cli decode --help
```

The tag is cut on `main` BEFORE the retirement branch is merged, so the tree
it names carries the whole v1 CLI: `decode --state <path>` (with
`--scan-dpi`, `--mopup`, `--refine`, `--diag`, `--diag-dir`,
`--diag-interval`, `--diag-panel-width`, `--profile-timing`, and the
discovery-first entry with neither `--coding` nor `--format`) opens an
archived state there exactly as e029–e035 ran it. On the retirement branch
itself the picture differs by one commit: `b167b9f` still has the receive
package but its `decode` is already the holo3-forwarding door (Phase 4.1),
so from that commit — or from any tree where the package is present but the
CLI is not — go one level under the CLI:

```python
from holo.receive.session import load_session
state = load_session(path)          # session.py:782
```

or the narrower slice `measure/parity/extract_holo1_certs.py` used — mmap
plus a string-aware scan of the top-level `"certificates"` array only, no
full deserialize (DELETION-LOG's table says where its result lives).
