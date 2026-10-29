# holo3 conversion record

The historical record of the holo3 build (2026-08-28/29): the plan and
charter, the frozen contract with its ~100 rulings and amendments, the
fourteen distillation specs (every constant with file:line provenance
from src/holo and holo2), the descriptor-system plan, the build-wave
reports, the leanness and integration-gap reviews, the per-tile gap
forensics (GAPS.md), the holo1-parity measurement (PARITY.md,
parity.json), and under verify/ the bit-exactness verification scripts
that gated every wave plus the acceptance manifest and the sim-capture
generator.

SNAPSHOT, NOT A LIVE GATE (recorded 2026-08-30): verify/ is pinned to
the wave that produced it and is NOT re-run against later trees. Three
of its scripts already name symbols that later rulings deleted —
`verify_color_region.py` (`stride_select`, removed with the 40k context
label cap; `RegionColorModel`, deleted by the "if only diag is the
customer, trash this" ruling) and `verify_tiles.py` + `verify_engine.py`
(`TileEvidence`, deleted with tiles.freeze in D6 Wave 2). They are
history and are left as written. Do not read "gated every wave" as
"passes today", and do not cite a green verify/ run as a gate: the
committed fast and slow lanes under src/holo/receiver/tests are the live gates.

RETIRED BY RULING (2026-08-31): the lead ruled "retire" — verify/ is
formally retired as a gate, permanently. It stays in the archive as
the record of what gated the conversion waves; nothing may be rewritten
against current mechanisms, and no future work owes it a green run.

Deliberately NOT carried: the sim capture tiffs (regenerate
deterministically with verify/make_sims.py from the main worktree,
oracle-confirmed shas in verify/acceptance.json), decode run
directories, and harvest artifacts — binaries, all reproducible from
the scans of record. The live working copies of everything here remain
in the gitignored _distill/ during active work; this directory is the
snapshot that travels with the tree.
