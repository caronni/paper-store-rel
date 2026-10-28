# Experiment 030 — first holo-v1 color pages (CMY8 / CMY7)

Status at 2026-08-05 (HP–Canon CMY8 chain closed out): **CMY8 volume NOT
recovered on either cell size.** Useful negative + partial positive on
the home engine. **CMY7 pages emitted same day for dual-engine print
(HP + Xerox)** — not yet printed/scanned.

- **c2-cmy8**: hard FAIL — 0 LDPC certificates after full 12/12 ladder +
  mop-up + refine; addressing only partially works; payload looks like
  washed screened mush (forensic GT-vs-scan).
- **c3-cmy8**: partial — **663 CRC-ok certificates (C 620 / M 43 / Y 0)**;
  fountain sees 663/402 headline K with reach 663/1206 over 3 stream
  blocks; metadata trusted; **close still OPEN** (Y stream empty; M far
  below a block). Not a decode.
- **c2/c3-cmy7**: pack7 single-stream rows emitted 2026-08-05 into
  `scratch/e030/holo-c{2,3}-cmy7-q05-counting/` (same `hp-m281` 6 mm
  geometry as Xerox registry — one `.ps` each, print on both engines).

Ties to e017.5/017.6 (M281 8-state toxic / Y-starved) and the layer-0
freeze (region-overlap CMY re-screens ~165 lpi on this engine). Xerox
AltaLink is the natural next print (healthy CMY, OPM escape hatch);
CMY7 avoids the CMY triple state that was toxic on M281.

## Objective

- First physical prints of holo format-v1 **CMY8** rows
  (`c2-cmy8-p120-v0`, `c3-cmy8-p120-v0`) on the locked home engine.
- Measure whether the production color receiver (furniture-QDA path,
  per-stream LDPC, level-stratified fountain-v2) can close a volume on
  M281+Canon, or whether e017's channel finding still binds.

## Sheets (emit record)

Both: `hp-m281`, margin 6.0 mm, counting payload, fountain q≈0.5,
codec `cmy8-presence-p120-v0`, streams C/M/Y with frozen rungs
**C/M r0550, Y r0547**, dust 20/tile, word states W vs CM.

| sheet | dir | spec | cells | tiles | payload | ps sha | data sha |
|-------|-----|------|-------|-------|---------|--------|----------|
| c2 | `scratch/e030/holo-c2-cmy8-q05-counting/` | `c2-cmy8-p120-v0@3328x2304` | 3328×2304 | 1872 | 718,413 B | `ad8bda94…` | `f13c34db…` |
| c3 | `scratch/e030/holo-c3-cmy8-q05-counting/` | `c3-cmy8-p120-v0@2240x1536` | 2240×1536 | 840 | 314,579 B | `97ce6b02…` | `a98e9935…` |

Volume (both): fountain-v2, 3 streams × 2087 symbol bits; c2 K=918/N=1872
(eff. K/N 0.490); c3 K=402/N=840 (eff. K/N 0.479). Seeds
`holo/v1/c2-cmy8-p120-v0/3328x2304` and
`holo/v1/c3-cmy8-p120-v0/2240x1536`.

### CMY7 pack7 (emitted 2026-08-05; print pending HP + Xerox)

Same printer row / margins (`hp-m281` 6.0 mm — field geometry matches
`xerox-altalink-c8245` at 6 mm, so one `.ps` per coding prints on both).
Codec `cmy7-pack7-p120-v0`, **single stream `main`** (no CMY triple
state), counting payload, q=0.5.

| sheet | dir | spec | tiles | payload | ps sha | data sha |
|-------|-----|------|-------|---------|--------|----------|
| c2 | `scratch/e030/holo-c2-cmy7-q05-counting/` | `c2-cmy7-p120-v0@3328x2304` | 1872 | 686,859 B | `2f94acc2…` | `5963b9d1…` |
| c3 | `scratch/e030/holo-c3-cmy7-q05-counting/` | `c3-cmy7-p120-v0@2240x1536` | 840 | 301,600 B | `a7d5dd25…` | `4f68dbf9…` |

Volume: c2 K=920/N=1872; c3 K=404/N=840. Seeds
`holo/v1/c2-cmy7-p120-v0/3328x2304` and
`holo/v1/c3-cmy7-p120-v0/2240x1536`.

```
scripts/print_plane.sh scratch/e030/holo-c2-cmy7-q05-counting/page000.ps
scripts/print_plane.sh scratch/e030/holo-c3-cmy7-q05-counting/page000.ps
```

Decode (emit printer, either physical engine):

```
./confetti.py decode <scan.tiff> --scan-dpi 4800 \
  --coding c2-cmy7-p120-v0 --printer hp-m281 --page 0 …
./confetti.py decode <scan.tiff> --scan-dpi 4800 \
  --coding c3-cmy7-p120-v0 --printer hp-m281 --page 0 …
```

## Print + scan log (HP–Canon)

| run | date | action | details |
|-----|------|--------|---------|
| 030.0p | 2026-08-04 night / 08-05 | print | HP CLJ M281fdw, raw 9100; both `.ps` from the dirs above (part of the same print-day wave as e028/e029) |
| 030.0s-c2 | 2026-08-05 ~00:20 | scan | Canon 4800 RGB → `scratch/e030/hp-canon-c2-cmy8-q05-counting.tiff` (6.875 GB), sha256 `cbd6c94d3a20c1ffbb9f426115dfe3611510b9f097f50c2f3d434f8f55fee1c9` |
| 030.0s-c3 | 2026-08-05 ~01:35 | scan | Canon 4800 RGB → `scratch/e030/hp-canon-c3-cmy8-q05-counting.tiff` (6.875 GB), sha256 `a8cc39ec48e7b8aab6ead1fd27ccb8d6c03645935d970ae6c3eb259450b62b2a` |

Capture ids in the receive states are the TIFF sha prefixes (`cbd6c94d3a20`,
`a8cc39ec48e7`).

## Decode

```
./confetti.py decode scratch/e030/hp-canon-c2-cmy8-q05-counting.tiff \
  --scan-dpi 4800 --coding c2-cmy8-p120-v0 --printer hp-m281 --page 0 \
  --refine --state scratch/e030/holo-c2-cmy8-q05-counting/receive.state \
  -o scratch/e030/holo-c2-cmy8-q05-counting/recovered.bin --diag --diag-port 8023

./confetti.py decode scratch/e030/hp-canon-c3-cmy8-q05-counting.tiff \
  --scan-dpi 4800 --coding c3-cmy8-p120-v0 --printer hp-m281 --page 0 \
  --refine --state scratch/e030/holo-c3-cmy8-q05-counting/receive.state \
  -o scratch/e030/holo-c3-cmy8-q05-counting/recovered.bin --diag --diag-port 8023
```

Receiver PROVISIONAL. Both retained states finished their ladders
(`done: true` in diag status); close remains `OPEN` on both (no
`recovered.bin`).

## RESULTS

### 030.1 — c2-cmy8 HP–Canon (FAIL)

From `receive.state` + `receive.state.diag/status.json` (frame 3349):

- 1 scrap located+placed; mapped footprint **45.1%** (3.36M/7.44M cells).
- Address: 721 accepted / 5139 unresolved placements; words 2 match /
  1060 insufficient / 161 refused.
- LDPC: 6586 calls, **0 certificates**, 1515 failed, 2229 low; scan
  `crc_ok=0`.
- Fountain: received 0; metadata rank 0/24; close deferred.
- Forensic: `scratch/e030/cmy8-gt-vs-scan-tiles.png` — accepted tiles show
  GT word counters OK but payload hard-BER ~chance; scan looks screened
  CMY mush at c2.

**Verdict:** M281 screened composite + c2 cell size is not a viable
CMY8 data channel on this engine (matches e025 “CMY8-at-c2 refused on
per-plane registration” / layer-0 screen tax). Not a receiver bug hunt
target until a healthier print exists.

### 030.2 — c3-cmy8 HP–Canon (PARTIAL, not closed)

From state (loaded) + diag status (frame 441), level 15/15 done:

- 1 scrap; mapped footprint **99.3%** (3.32M/3.34M cells).
- Address: 1381 accepted / 379 unresolved; words 78 match / 629
  insufficient / 133 refused.
- LDPC: 35281 calls; **663 certificates** (scan crc_ok 621 + retry150
  crc_ok 42); 1842 failed; 15 low.
- **Per-stream certificates: C 620 / M 43 / Y 0** (C∩M only 31 tiles).
- Fountain UI: received 663/402 K, reach 663/1206 over 3 blocks,
  metadata trusted; **rank/solve deferred, close OPEN**.
- Counters: `divergences=663` (= cert count) — treat as a display/ledger
  curiosity until audited; CRC path is what certifies bits here.

**Verdict:** Geometry and the C plane are alive at c3; M is marginal; Y
is dead on this print (e017 Y-starved / triple-toxic pattern). Aggregate
certs cannot close a 3-stream volume with Y=0. This is a **channel /
engine** result for M281 CMY8, not a format retraction.

## Session side-findings (diag, not channel)

During the c2 decode, mop-up pane-A overlays piled purple/gray planned
windows into a corner of the pane. Diagnosed 2026-08-05 and fixed at the
cause; the first two attempts (32345ef, and an uncommitted follow-up)
were both wrong about the mechanism and are recorded here because the
misdiagnosis is the instructive part.

- **Cause**: an M/R level reuses its BASE lane's raster, so it emits that
  lane's pixel coordinates, while pane A's underlay belongs to whichever
  ladder rung surveyed last. Base-lane boxes drawn through a ~12x finer
  transform compress toward the pane origin at 1/12 size. `_planned`
  boxes had ALWAYS been projected through a single mutable
  `_scan_transform`; the bug arrived with the v0.42 M-levels, not with
  any commit that touched the viewer.
- **Not the cause**: 32345ef's "empty mop-up survey keeps the prior
  transform" clause. It sits inside `_ingest_survey`, behind a snapshot
  gate that a production M/R `survey.complete` (details only, no
  `snapshot_factory`) never passes. It could neither cause nor prevent
  this. 32345ef fixed a different, real defect — e028's pane-frozen amber
  chips. The uncommitted follow-up patched the same unreachable branch
  and was dead code; both attempts looked green because no test in the
  tree had ever driven the production-shaped M/R survey event.
- **Fix** (RECEIVE-DESIGN v0.47, commit 74d0a9b): `LaneSpec.native_per_view`
  — which `_scale_plan` already copies verbatim onto M/R lanes — is
  published on `level.open`/`lane.open` and folded into
  `EventContext.native_per_view`; the viewer normalizes every pane-A box
  to CAPTURE-NATIVE px at ingest and keeps ONE transform. The per-lane
  transform registry, both snaps and the chip fallback are deleted. The
  higher-volume half was `_active_scan_box`, frozen to pane px at ingest
  and mis-projected on every real run (~8,900 events on c3 m00).
- **Companion defect found in the same pass** (v0.48, commit 81e5554):
  region ordinals are LANE-RELATIVE, so an M/R level's `address.region`
  addresses its base lane's regions while the views on screen belong to
  another rung — the wrong scrap lit up, and `rows._scraps_row`'s counts
  mixed two segmentations. Both directions reproduced.
- Pane A then became its own module (v0.49, commit 11217e0):
  `diag/scan_model.py`, viewer.py 1229 -> 965.

Tests in `tests/holo/test_diag_viewer.py` — both pins drive the
production-shaped event and were verified failing without their fix.

## Print-day context (2026-08-04 → 08-05)

Same wave as:

- e028 HCAL discovery B/W + color (M281), knife-edge / ink geometry,
- **e029** first holo-v1 K-only volume — hardware VERIFIED (465,580 B,
  64.7 b/mm² field),
- **e030** these CMY8 pages (HP print + Canon RGB decode above).

Queued dual-engine prints (HP + Xerox): both e030 CMY8 `.ps`, both
**CMY7** `.ps` (`holo-c{2,3}-cmy7-q05-counting/`), plus earlier e028
riders as planned. CMY7 is the pack7 single-stream alternative to the
toxic triple.

## Caveats

- ONE engine (M281), ONE scanner (Canon), one day each sheet. No rate
  ladder, no CMY8 format promotion, no receiver qualification.
- Decode uses emit `--printer hp-m281` even if a future print is on
  Xerox — seed/geometry follow the emit row.
- Operator media/tray/density not separately recorded.
- c3 close was not forced with an extra `--complete` after Y-empty was
  already visible; further harvest cannot mint Y certificates from this
  raster.

## Artifacts

- `scratch/e030/holo-c2-cmy8-q05-counting/` — emit + `receive.state` (~81 MB)
  + diag; no recovered payload.
- `scratch/e030/holo-c3-cmy8-q05-counting/` — emit + `receive.state` (~634 MB)
  + diag; no recovered payload.
- Scans + `scratch/e030/tiff-shas.txt`.
- Forensic `scratch/e030/cmy8-gt-vs-scan-tiles.png`.
- Durable memory: `.claude/memories/e030-holo-cmy8-hp-canon.md`.
