# paper-store, the tree of 2026-09-04

> **This commit is the historical tree**: the private working tree of 2026-09-04.
> The project, the pictures and the current commands are on the latest commit.
> Experiments 036 onward are not in this tree: Sheet H, the bootstrap and the
> colour record.

Data storage on plain laser-printed paper: a file is written as PostScript for
an unmodified office laser printer and read back from flatbed scans. The page
carries no fiducials; known pilot cells inside the data address each tile, an
LDPC code with a CRC certifies it, and an outer fountain code rebuilds the
file from any large enough set of certified tiles, from any pages or
fragments.

## What this commit is

The first commit of this repository is the project's private working tree of
2026-09-04 (the tag `pre-v1-v2-deletion`). It is published because it is the
last tree that holds every receiver architecture the documents of record
describe, side by side, together with the analyzer of the day:

- `src/holo`: the format and generator, and `src/holo/receive`, the v1
  receiver (`./confetti.py generate`, `./confetti.py decode`); normative
  `docs/HOLO-DESIGN.md` (library and format) and `docs/RECEIVE-DESIGN.md`
  (receiver).
- `holo2/`: the holo2 receiver restart, tile-map authority and dataflow
  workers (`./confetti2.py`; its design in `holo2/README.md` and
  `holo2/docs/`).
- `holo3/`: the holo3 receiver, still at the repository root
  (`./confetti3.py decode`; normative `holo3/API.md` and `holo3/SCHEDULE.md`).
- `analyzer/`: the blind yield maximizer over holo3 snapshots
  (`env/bin/python -m analyzer`; `analyzer/README.md`).
- `src/paperholo` with `experiments/001-026`: the v1 research stack and its
  measured record; `docs/DESIGN.md` is the v1 specification.
- `experiments/027-035`: the measured record of the holo era (printer
  characterisation and discovery, the first holo prints, payload volumes and
  rung experiments, the sheet I and sheet J readouts).
- `measure/`: the instruments that read the measured record.
- `tests/`: `tests/holo` (src/holo), the paperholo lane at its top level,
  and `tests/holo2_oracles` (holo2).

The day after this tree, holo2 and the v1 receiver were deleted and holo3
moved to `src/holo/receiver`. `holo3/retirement_docs-2026-09/` is that
campaign's record as of this tree: gates A and B passed, the comment carry
(gate C) under review, the holo2 deletion and the v1 receiver retirement
(gates D and E) still open, nothing deleted yet; the deletions are recorded
in the next commit. Every document here speaks as of its own date.

## Running it

One virtualenv, `env/`, at the repository root, built on free-threaded
CPython 3.14 from `requirements.txt` (its header gives the commands). Nothing
is pip-installed: `pyproject.toml` and `conftest.py` put `src/` and
`holo2/src/` on the path. The launchers start with `#!env/bin/python` and run
from the repository root.

The test lanes of the day, from the repository root:

```sh
env/bin/python -m pytest                    # pyproject's testpaths: tests/ and holo2/tests/
env/bin/python -m pytest tests/holo         # the generator and the v1 receiver
env/bin/python -m pytest holo2/tests tests/holo2_oracles   # holo2
env/bin/python -m pytest holo3/tests        # holo3, fast lane
env/bin/python -m pytest analyzer/tests     # the analyzer
```

`HOLO_RUN_SLOW_TESTS=1` adds the slow cases of `tests/` and `analyzer/tests`,
`HOLO3_RUN_SLOW_TESTS=1` the sim decodes of `holo3/tests`. The package
versions `requirements.txt` names are floors; a newer release than the one of
2026-09-04 can fail a test that passed then. Tests that read untracked
capture or scratch inputs skip or fail on a fresh clone, and one needs a git
checkout. Measured on this tree on 2026-10-27 (an untracked copy, the
free-threaded CPython 3.14 venv of that day): `pytest` 5,059 passed and 54
skipped with eight workers, the three pins of records rewritten on export
updated first; `holo3/tests` 1,807 passed,
458 skipped, 1 failed (`test_h3_conventions.py::test_holo3_test_basenames_are_unique_against_every_tracked_repo_file`
lists the tracked files with git); `analyzer/tests` 475 passed, 75 skipped,
1 failed (`test_analyzer_score.py::test_a_row_beyond_the_reconstructed_pages_refuses`
reads a payload under the untracked `scratch/`). Whether every lane was green
on 2026-09-04 in the working tree it was cut from is not recorded.

### Sample commands

A few sample commands exercise the tree's own generator and its v1 and holo2
receivers, which exist in no later commit. Measured on this tree on
2026-10-28, from the repository root with `env/` built (no `PYTHONPATH`):

```sh
./confetti.py generate --help   # the --format grammar, the --paper bundles, `fit`
./confetti.py generate --format c2-k-r0700@53x37 --paper A4-4mm \
  --source-fraction 0.5 -o gen-k payload.bin
./confetti.py generate --format c2-cmy8-r0700@53x37 --paper A4-4mm \
  --source-fraction 0.5 -o gen-cmy8 payload.bin
```

`payload.bin` is any file up to one page's capacity at q 0.5: 330,977 bytes
for the black row, 997,023 for the cmy8 row (`./confetti.py capacity` with
the same flags and `--pages 1`; the rung and q set it, and a lower q buys
repair tiles at the expense of bytes). A 53x37 matrix needs `--paper
A4-4mm`; the default A4-6mm fits 52x36, and `fit` gives the largest matrix
for a paper. For a 4,096-byte payload each run takes seconds and writes
`page000.ps` (8.1 MB black, 32.4 MB colour), the ground-truth bitmap
`page000_gt.npy` and the sidecar `manifest.json`. The sheets of the record
predate this grammar and decode through their `L:` lines:

```sh
./confetti.py decode <k-capture>.tiff --scan-dpi 4800 \
  --format L:c2-r0700@3392x2368 --workers 8 --diag --diag-port 8026 \
  --diag-dir diag-k --state k-state.bin -o k.bin
# VERIFIED 465,580 bytes, sha256 e5021f8d0995..., 1,848 certificates,
# 4 min 26 s with 8 workers
./confetti.py decode <cmy8-capture>.tiff --scan-dpi 4800 \
  --format L:c2-cmy8-p120-v0@3328x2304 --workers 8 --diag --diag-port 8027 \
  --diag-dir diag-cmy8 --state cmy8-state.bin -o cmy8.bin
# VERIFIED 718,413 bytes, sha256 f13c34db6c96..., 3,981 certificates
# (C 1,256, M 1,424, Y 1,301 of 1,872 each), 4 min 32 s with 8 workers
./confetti2.py --scan <k-capture>.tiff --dpi 4800 \
  --format L:c2-r0700@3392x2368 --workers 8 --diag-port 8024 \
  --state-dir k-holo2 --output k-holo2.bin
# VERIFIED 465,580 bytes, sha256 e5021f8d0995..., 1,356 certified tiles
# (exactly K), about 9 min with 8 workers
```

Both receivers warn on every run that they are provisional; holo2 refuses
colour at this tree ("holo2 cannot decode cmy8"). v1 serves a live view at
`http://127.0.0.1:<port>/` with `--diag --diag-port`; holo2 always serves its
status on `--diag-port` (default 8024). The captures are experiment 032's c2
sheets, printed on the Xerox AltaLink and scanned on the Canon at 4800 dpi:

- `032-xerox-altalink-payload-volumes/altalink-c2-k/captures/c2-k-canon-4800grey.tiff`,
  black, grey: 2,291,818,718 bytes,
  sha256 `57a261454cc04e66bd333310df4d17ede867eaa862fe6cff20e5395799d927e3`
- `032-xerox-altalink-payload-volumes/altalink-c2-cmy8/captures/c2-cmy8-canon-4800rgb.tiff`,
  colour, q 0.5, RGB: 6,875,455,728 bytes,
  sha256 `cf6427d0d66a3cb9af0b74f7162f5b163dd2f2f75bcf162940326ef6cc8aec47`

They ship in the evidence release `paper-store-evidence-holo-2026-10` as
JPEG XL plus a header. This tree predates the evidence releases; the README
of the latest commit (section "First run") describes the release and the
`tools/unpack.sh` recipe that rebuilds each capture byte for byte.

## Reading it

- This is a squashed export, one commit per published tree. The commit shas,
  tags and branch names cited in the text resolve only in the private
  repository the export was cut from.
- Files the record names but does not carry (plans, rulings, reviews, agent
  notes, working drafts) were withheld as working papers; pointers at them
  are left as written.
- Private strings were replaced on export: angle-bracket tokens such as
  `<ip>`, `<host>`, `<home>`, `<tmp>`, `<volume>` and `<city>` stand for the
  removed string, and "machine N" names one of the author's workstations.
  Absolute paths into the author's checkout are written relative to the
  repository root, and the bare root as `<repo>`; a path into another
  checkout of the author's (a sibling worktree) begins with `<checkout>`.
  A code constant rewritten this way runs only from the repository root (a
  relative path), or not at all (`<repo>`, `<checkout>`, `<home>`, `<tmp>`).
- Records rewritten on export no longer hash to the sha256 values cited for
  them elsewhere in the tree (the citations are left as written); the three
  test pins of rewritten records were updated.
- Sections of some design documents (build records, workplans, a condensed
  design dialogue) were cut on export; their section numbers keep the gap.

## Licence

MIT; see `LICENSE`.
