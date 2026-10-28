# e034 — Sheet I read to 99.95%: the four-run resume chain (2026-08-31)

**Headline: 5,880 of 5,883 tile-streams certified on sheet I —
99.949% of the physical page — close VERIFIED byte-exact
(1,798,761 bytes, sha256 `2445b95db5b49bf3…`, identical to the e033
emission) on every closing run of the chain. The M plane is COMPLETE
(1961/1961); C 1960/1961; Y 1959/1961. Three tile-streams on the
whole sheet resisted everything the receiver has.** Zero wrong
certificates anywhere in the chain (codec-gated throughout).

Sheet I is the e033 print: Xerox AltaLink C8245,
`L:c2-cmy8-r0700-p120-x1@3392x2368` (fossil id; 53 tile rows × 37
tile columns = 1,961 tiles × 3 streams = 5,883 tile-streams;
k_total 5,277), 230.7 b/mm² field. History of this same sheet:
holo1 read 5,297 certificates; holo3 pre-arms-wave read 5,445.

This log is the receiver-side campaign record. It is also the first
production use of the lean fact-snapshot resume, the first real-paper
yield of tiles.planek / tiles.swim / the honest-units plane fields,
and the second measured data point on the 4800 question. Machine:
machine 2 (64 GB), 12 workers throughout. Data curated from the
run dirs by a six-agent extraction pass over `report.json` +
`events.jsonl` + `facts.npz` (read-only); events archived under
`scratch/sheetI-20260831/`.

## The chain

| run | tree | captures | wall | cpu-s | new certs | close |
|---|---|---|---|---|---|---|
| 1 `holo3-I-first-run` | `eee976c`-era (pre-units-fix fields) | 3×2400 | ~4h35m | 175,681 | 5,543 (C 1949 / M 1960 / Y 1634) | open (`--no-close`), 266-symbol margin |
| 2 `holo3-I-resume-run` | main post-units-fix, pre-hybrid | same 3 | ~2h44m | 109,910 | **+323** (Y 313 / C 9 / M 1) | **VERIFIED** 5,866, surplus 589 |
| 3 `holo3-I-resume-2-run` | main `858d4db` (hybrid landed) | same 3 | ~8.5m | 4,193 | **0** | VERIFIED 5,866 (replay) |
| 4 `holo3-I-resume-3-run` | main `858d4db` | +1×**4800** | ~22.5m | 12,639 | **+14** (Y 12 / C 2) | **VERIFIED 5,880**, surplus 603 |

Captures: Canon 4800-class flatbed, RGB. Three 2400 dpi scans
(sha12 `a410631d`, `36b90a50`, `269d8121` — two are deliberate
re-placements, per the multi-scan law), one 4800 dpi scan
(`5d24205330ff`, ingested only in run 4). Every resume folded the
prior run's `facts.npz` through the ordinary merge path
(SnapshotReplayed marker in each event stream; fold_errors 0
everywhere). Wall times from file mtimes — holo3 events carry no
wall clocks by law (verified: no time-like key in any event type).

Total chain cost ≈ 302,400 cpu-s ≈ 84 cpu-hours for the whole page.

## Run 1 — the from-scratch base (5,543)

The ordinary rows did the mass work: tiles.scan 4,723, union 327,
retry 280, local 213. The colour/field late-stage plugins minted
zero — this tree's field fitter was the pre-units-fix one (54 fits,
zero PlaneField facts published; the defect record is in
holo3/conversion_docs/ARMS-2026-08-31.md). tiles.local consumed 73%
of the run's CPU (129,017 cpu-s) for its 213 — the known cost
profile. Y closed at 1,634/1,961 (83.3%) with 91,880 failed Y
attempts against 12,893 C / 5,893 M: the AltaLink Y x-registration
dead bands drawn in attempt churn.

Provenance caveat: this run dir's `argv` was later OVERWRITTEN by a
subsequent resume launch (mtime 6 h after run end, placeholder
resume path, names the resume-1 out/run-dir), which also re-touched
the per-capture level caches. The event stream proves the run was
from-scratch (no replay marker; first CloseCheck at certified=3).
The launch flags for this run come from the session record
(`--no-close`), not from the on-disk argv. → Run-dir artifacts
should be treated as append-only; a launch that resumes FROM a dir
must not write INTO it.

## Run 2 — the planek avalanche (+323)

The arms-wave tree (honest-units fields, planek, swim, uplift,
repricing, done-geometry) attacked the 340-tile residue. Net new:
**tiles.planek 281 (Y 275, C 5, M 1), tiles.local 26, tiles.retry
10, tiles.swim 6** — the swim's first real-paper certificates.
96.9% of the new yield is Y.

**The cascade is measured, not inferred** (predecessor = same-run
certificate in the 8-neighbourhood at mint time; replayed certs
excluded as uniform baseline):

- 82% of planek's 281 had ≥1 same-run neighbour predecessor
  (mean 2.21); 51 seeds, 230 descendants; chains reach
  **7 generations**; 88% of feeding edges are planek→planek.
- The avalanche body is temporally sharp: the middle 50% of planek
  mints land inside 9.8% of the journal (event-sequence axis).
- Zero planek mints had a same-run sibling certificate at the same
  tile — the sibling-subtraction inputs were replayed C/M
  certificates. The avalanche is a within-plane (Y) chain reaction
  fed by cross-plane truth that was already standing.

Economics: planek earned 281 certificates for 2,278 cpu-s —
**8.1 cpu-s per certificate** — while tiles.local spent 78,700
cpu-s for 26 (~3,000 cpu-s each). The per-tool accounting for any
future pricing conversation.

Close VERIFIED at 5,866 — sheet-I best-ever at that point, +421
over holo3 pre-arms and +569 over holo1.

## Run 3 — the current-tree control (+0)

Fresh pull (hybrid tiles.local landed), same three captures: 1,039
jobs, 4,193 cpu-s, all 17 residual tile-streams attempted (incl. 51
swim jobs), **none certified**. This is the honest floor of three
2400 dpi captures under the current toolbox — and the residue's
identity: C at (0,0), (22,21), (35,29); Y at (0,0), the tx 10–11
top-row block, the (36, 15–17) run, and (36,27)/(36,29).

## Run 4 — the 4800 capture answers (+14)

One added 4800 dpi scan bought **14 of the 17**: planek 9 (net),
local 2, union 1, retry 1, swim 1 — Y 12, C 2. Even the +14 is
cascade-shaped: the top-edge Y block (rows 0–2 × cols 10–11) filled
in chains with up to 5 same-run neighbour predecessors, and the
(36,16) middle tile certified last with both flankers as
predecessors. The very last mint of the campaign is the swim
recovering (0,0,Y) on the damaged corner.

**The 4800 question, second data point**: on the defective-scheduler
tree the seven-capture H stack measured −70 and the "native noise
pollutes the unions" story was already rejected on its merits
(unions pair at shared rungs where 4800 contributions are
decimated). Here, on the fixed tree, a 4800 capture added +14 on a
page where three 2400s were provably exhausted (run 3's zero).
Adding Canon 4800 captures HELPS. Machine 4 sheet-H formal pair remains
the controlled experiment; this is the existence proof.

## The three that remain

1. **(0,0,C)** — the page-corner tile, 565 attempts across the
   chain, BP to the 300-iteration cap, zero successes. Local damage,
   not a plane effect: the same tile's M certified only via retry,
   its Y only via the swim on the 4800 capture, while all three
   planes of every neighbour certified via plain scan.
2. **(36,27,Y)** and **(36,29,Y)** — 685/692 attempts; the last two
   unrescued residues of the deepest Y dead band (tx 27–30),
   flanking the worst column tx=28, whose Y tiles needed rescue
   arms for **all 53 rows**.

The dead-band geography, recovered from certificate *sources*
(rescue-arm fraction per column, since final totals are now
saturated): bands at tx 7–11, 15–19, 27–30 — centers ~9 columns
apart ≈ 49 mm ≈ half-period of the measured ~100 mm Y-registration
sinusoid (e033). Fully dead columns hold ~12.8% cell error against
a rate-0.859 rung (the planek rate-fact): the remaining two Y tiles
are format-axis losses, exactly where the format's own algebra says
they should be.

## The field record

All lanes, all runs with the honest fitter: **C published**
(median 0.363–0.374 dots at 2400; **0.53–0.60 dots on the 4800
lanes**), M refused (0.228–0.236d, just under the 0.25 floor;
0.14–0.18d at 4800), Y refused (0.11–0.17d everywhere). Residuals
0.985–0.991 (the field explains ~1% of per-site energy — the
systematic part is small vs channel noise, as a healthy sheet
should be). The C magnitude corroborates the independently measured
printer per-plane grid magnification by-catch (+0.306 dots); the
suspiciously low Y median vs the 0.83-dot sinusoid peak is
consistent with the standing photometric-gain anomaly (reads
0.46–0.53 of real printer displacement) meeting Y's dust-only
anchor supply — both open in conversion_docs/OPEN-2026-08-31.md.

## Resume mechanics, first production outing

Each fold: single SnapshotReplayed event, families
Certificate/Window/Placement/LatticeSeed/CaptureSurvey/
PooledColorCtx (+PlaneField once the honest fitter wrote them),
fold_errors 0. Replay of 5,866 already exceeded k_total, so run 4's
close rode replay+14. Snapshot sizes ~194–228 MB compressed. The
run dir answers the provenance questions natively: `argv` (exact
command line) + `report.json` (final status, close verdict,
scheduler table, churn, plane fields, replayed counts) are written
at run end — subject to the append-only caveat above. The tree sha
is NOT recorded anywhere in the run dir (this log's tree column
comes from the operator's shell) — the one provenance gap.

## Standing rules check

Single sheet, single print day, one engine pairing: existence and
regression evidence, **no ladder promotion, no population claim**.
Receiver status remains PROVISIONAL. Certificates are codec-gated;
the byte-identical close sha on three independent closes is the
end-to-end truth anchor.

## Artifacts

- `scratch/sheetI-20260831/` — per-run `argv`, `report.json`,
  field/page panes, and the four `events.jsonl.xz` (~73 MB raw).
- `facts.npz` snapshots stay on machine 2 (`/tmp/I/…`, 1.7 GB + 3×
  ~200 MB) as resume seeds; payload `holo3-I-resume-3.bin` verified.
- Extraction scripts: session scratchpad (six-agent read-only pass);
  derivations reproducible from the archived events + snapshot.
