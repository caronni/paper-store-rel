# crop_parity — holo1 vs holo3 on crops, in seconds

Full-sheet parity runs cost 11 minutes to 1h52m and tens of GiB. This
package answers the same per-tile question on a crop cut around the
tiles in dispute: **seconds to a couple of minutes, hundreds of MB.**

It is a port of the holo1-vs-holo2 crop harness in the MAIN worktree
(`holo2/measure/crop_cases.py`, `crop_harness*.py`) with the holo2 side
replaced by holo3 and the case source replaced by the holo3 parity
record under `_distill/verify/parity/`.

Instruments live in `measure/` (the standing ruling). Nothing here is a
test and nothing here is collectable as one; nothing here writes to
`holo3/`, and the main worktree is READ-ONLY — its interpreter and CLI
are *run*, its scans and states are *read*, and every artifact this
package produces lands in this worktree's gitignored `scratch/`.

## Invocation

Always from the worktree root, always with `PYTHONPATH=.`:

```sh
cd <checkout>

# 1. cases: cut the crops and write the manifest
PYTHONPATH=. env314t/bin/python -m measure.crop_parity.cases \
    --volume e029

# 2. harness: run BOTH receivers on every case, compare, report
PYTHONPATH=. env314t/bin/python -m measure.crop_parity.harness \
    --volume e029

# the inner loop: one case, holo3 only (holo1's standing sidecar still renders)
PYTHONPATH=. env314t/bin/python -m measure.crop_parity.harness \
    --volume e029 --case e029-c01 --side holo3

# 3. self-check: pure geometry + the address frame on a synthetic case
PYTHONPATH=. env314t/bin/python -m measure.crop_parity._selfcheck              # ~55 s
PYTHONPATH=. env314t/bin/python -m measure.crop_parity._selfcheck --skip-decodes
PYTHONPATH=. env314t/bin/python -m measure.crop_parity._selfcheck --with-holo1
```

The self-check's holo1 arm is opt-in: holo1 decoding the whole sim page
with the `--mopup --refine` ladder passed 20 minutes and 7.9 GiB without
finishing (measured 2026-08-29). The holo3 arm runs by default in ~55 s,
and holo1's frame is covered by the battery itself — 40 holo1
certificates on the e029 case with zero out-of-bbox and zero GT
mismatches, which a shifted frame cannot produce.

Useful flags: `--classes miss,gain,neither` (default `miss,gain`),
`--halo-cells`, `--merge-gap-tiles`, `--max-span-cells` on `cases`;
`--fresh`, `--side`, `--workers`, `--timeout` on `harness`;
`--crosscheck` on `cases` re-reads the holo1 state through its own
`load_session` and compares.

Exit codes on `harness`: `0` healthy, `2` a wrong certificate was found,
`3` ground truth refused validation.

## The volumes

Declared in `_volumes.py`, one per parity step, with the holo3 harvest
whose certificate set defines the gap:

| key | step | format | baseline | miss | gain | colour |
|---|---|---|---|---:|---:|---|
| `e029` | 2 | `L:c2-r0700@3392x2368` | `post-2` | 2 | 0 | no |
| `xerox-k` | 5 | `L:c2-r0700@3392x2368` | `post-5` | 5 | 2 | no |
| `xerox-c3-cmy7` | 3 | `L:c3-cmy7-p120-v0@2240x1536` | `post-3` | 0 | 95 | yes |
| `xerox-c2-cmy8` | 4 | `L:c2-cmy8-p120-v0@3328x2304` | `run-4` | 36 | 88 | yes |
| `xerox-c2-cmy7` | 6 | `L:c2-cmy7-p120-v0@3328x2304` | `post-6` | 26 | 31 | yes |
| `sheet-I` | 7 | `L:c2-cmy8-r0700-p120-x1@3392x2368` | `post-7` | 34 | 176 | yes |

`post-4` was killed at the 58 GiB ceiling and never measured, so volume
4's baseline stays `run-4`. Both sides are recomputed from the two
primaries (the `holo1-*.json` extract and the run dir's `events.jsonl`)
and cross-checked against the recorded counts; a mismatch refuses the
run.

**Colour caveat.** A crop changes the context a colour calibration head
pools over. Colour cases are therefore SCREENS: a crop verdict that
disagrees with the full-sheet record on a colour volume is evidence
about the crop first, and about the receiver only after a full-sheet
confirmation. The two K volumes carry no such caveat.

## How it works

* **Case generation** (`cases.py`). Targets are the selected classes'
  addresses; their tile positions are clustered (Chebyshev, by empty-tile
  gap), split to a span cap, given a halo, mapped to capture pixels
  through a per-capture affine fitted from the archived holo1 state's
  accepted poses, padded by 32 cells' worth of pixels, and cut off a
  read-only memmap at native pixels. Controls are the both-certified
  addresses fully inside the case's cell rectangle shrunk by a 32-cell
  rim, excluding every tile position that carries a target.
* **The holo1 side** (reference, once ever). The main tree's own
  interpreter runs its own `confetti.py decode … --no-close --complete
  --mopup --refine`, verbatim as the holo2 harness ran it.
* **The holo3 side** (`_h3run.py`). holo3 keeps no state file and no
  event carries certificate bits, so this entry parses the decode argv
  with holo3's OWN parser, builds the request with `cli._request`, runs
  `engine._Engine(...).run()` — what `cli._decode` calls — and dumps the
  store's certificates. The run dir still gets the CLI's `events.jsonl`
  and `report.json`. If a refactor moves those seams it falls back to
  the plain CLI and marks the bits unavailable, never a silent zero.
* **Ground truth** (`_gt.py`). The volume's recovered payload
  (sha-verified) is re-encoded through the MAIN tree's `src/holo`
  generation arithmetic into per-tile user bits — K, per-stream colour
  and pooled colour each following their own emitter — and validated
  against every certificate in the archived holo1 state before anything
  is reported. Measured green: e029 1,940/1,940, xerox-c2-cmy7
  1,559/1,559, xerox-c2-cmy8 5,370/5,370, zero mismatches.
* **Sidecars.** Every run writes `<runs>/<case>/<side>.sidecar.json`
  keyed on the crop sha, the side's receiver tree object and its dirty
  diff sha. holo1 (a frozen tree) decodes each case once ever; holo3
  re-decodes exactly when the holo3 receiver moved. Cache location:
  `scratch/crop-parity/<volume>/runs/<case_id>/`.

## The address frame

A crop shifts the page origin in PIXELS but not in ADDRESSES: a printed
tile carries its own absolute address word (C1, an 18-bit flat counter
under BCH), so a receiver that locks onto a crop recovers the same
`(page, ty, tx)` the full sheet would. Nothing here shifts an origin by
hand — the frame is read, and then CHECKED three ways:

1. every crop certificate must address a tile inside its case's cell
   rectangle (reported per battery as `out_of_bbox`);
2. every crop certificate's bits must equal ground truth — a one-tile
   shift would put a real certificate at a wrong address and fail here;
3. `_selfcheck` decodes the K simulation page whole and then a crop of
   it, and requires every crop address to be a full-page address.

## Measured, 2026-08-29 (the smoke proof)

Case generation, all six volumes, from the recorded parity record:

| volume | cases | targets | biggest case | crop px | crop MB |
|---|---:|---:|---:|---|---:|
| `e029` | 1 | 2 miss | 2 tiles | 9736x12819 | 124.8 |
| `xerox-k` | 5 | 5 miss + 2 gain | 2 tiles | 12821x5910 | ~76 |
| `xerox-c3-cmy7` | 8 | 95 gain | 35 tiles | 15772x6755 | ~320 (RGB) |
| `xerox-c2-cmy8` | 16 | 36 miss + 88 gain | 17 tiles | 17187x13063 | ~670 (RGB) |
| `xerox-c2-cmy7` | 20 | 26 miss + 31 gain | 9 tiles | 18977x8983 | ~510 (RGB) |
| `sheet-I` | 26 | 34 miss + 176 gain | — | — | x3 captures |

Generation is ~1 s per K volume including the crop write. The gap counts
recomputed from the primaries matched the recorded parity record exactly
on all six volumes, and ground truth validated against every archived
holo1 certificate on every volume it was run for.

**`e029-c01`, both sides, real e029 scan** (crop 9736x12819 px = 124.8 MB
out of the 2.29 GB capture, 2 target tiles + 66 controls, `--workers 1`):

| side | wall | crop certificates | GT-checked | wrong | controls |
|---|---:|---:|---:|---:|---|
| holo1 | 421.2 s | 40 | 40 | 0 | 32/66 |
| holo3 | 382.3 s / 441.1 s | 41 | 41 | 0 | 33/66 |

(holo3 twice, against two different working states of `holo3/` — same 41
certificates, same target verdicts both times; the wall moves with
machine load.)

Zero out-of-bbox certificates. Both sides agree on both targets: (42, 12)
uncertified, (42, 15) **certified on the crop by both** — a full-sheet
holo3 miss that the crop recovers. Adoption verified: the second
invocation adopted holo1's sidecar in 0 s and re-decoded holo3 only,
because another worker's edit to `holo3/` had moved the receiver's dirty
sha.

**Read control flips against rim depth.** Both receivers lose the same
controls, and the loss is a gradient in how deep the tile sits inside the
crop's cell rectangle — 16/30 flipped in the outer 64 cells, 0/2 in the
deepest ring, on BOTH sides. A crop starves its rim of context; that is
a property of cropping, not a receiver fact, and it is why targets sit at
halo depth (240 cells) by construction. The battery reports the
by-rim-depth table per case so the two are never confused.

**The K-sheet crop still costs minutes, not seconds.** A 400k-cell crop
(5% of the sheet) at `--workers 1` runs ~6-7 minutes a side against
~11 minutes for the whole sheet at `--workers 8`. The win is not yet the
per-run wall: it is that the reference side decodes ONCE EVER, that a
holo3 iteration re-decodes one case instead of a sheet, and that the case
is 125 MB instead of 2.29 GB. Raise `--workers` and lower `--halo-cells`
when the question tolerates it.

## Reading a battery

`crop-battery-<volume>.md` and `results.json` land beside the manifest.
Wrong certificates render at the top (expected: none). Control flips are
REPORTED, never gated — invented bars are retired. An unavailable side
is an em dash, never a fake miss.
