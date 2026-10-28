# e018 `--diag` live diagnostic viewer — design note

A live, per-piece view of the confetti session decoder
(`session_decode.py`). Watch each scrap get segmented, routed, placed (or
refused), and land on the archive page, while the LDPC/fountain progress
fills in. A "to be used later" instrument — correctness and a clean,
additive diff matter more than speed.

## Invocation

```
env/bin/python experiments/018-confetti-c3-play/session_decode.py \
    <img> [<img> ...] --dpi 1600 --piece-chain anchor \
    --diag scratch/diag --diag-port 8018
```

- `--diag [DIR]` turns the viewer on. `DIR` (default
  `experiments/018-confetti-c3-play/scratch/diag`) receives the numbered PNG
  frames (`frame_00001.png` …) as a durable record.
- `--diag-port N` (default `8018`; `0` = OS-assigned ephemeral) is the web
  view port. The driver prints the URL on start:
  `[diag] live view at http://localhost:8018/`.
- Open that URL in a browser. It polls once a second and swaps in the latest
  frame; the status line shows scan / piece counts / frame number.
- **Absent `--diag`, the decode path is byte-identical to a plain run** — the
  hook is a pure read-only observer (regression-tested, see below).

## What the user sees

One composite image, two spatial panels side by side, refreshed **per piece**:

- **A · active glass** (left) — the current scan, downsampled once, with every
  piece drawn in its **tilted** (de-rotated) frame as it is processed:
  - colour = live status: green `word` (word/tiled path decoded), blue
    `placed` (correlation-placed), red `failed` (refused / nothing emitted),
    amber = the piece currently in flight (transient outline);
  - an angle-estimate label per piece (`<index> <±deg>°`);
  - for placer pieces, the pilot **sites the receiver sampled**
    (`place.fragment_pilot_sites`) dotted in **magenta, in the piece's own
    rotated lattice frame**, mapped back to glass pixels. Boxes and dots
    accumulate on a persistent overlay, so the glass fills in as the scan is
    worked.
- **B/C/D · reference page** (right) — the absolute archive page, straight from
  `PageDecodeState`, reusing `draw_decode_map`'s panels: **B** each piece's
  payload footprint at its page position (per-piece tints), **C** LDPC tile
  status (certified / failed / low-cov), **D** acquired pilot tiles.

## Architecture

- `diag.py` — `DiagViewer`, the observer object, plus its stdlib web server.
  It lives in the experiment directory (not the `paperholo` package) because
  it is coupled to this driver's routing semantics and reuses this
  experiment's own `draw_decode_map` renderers; the reusable primitives it
  leans on (`segment.rotate_transform`, `place.fragment_pilot_sites`, the
  panel functions) already sit in their proper homes.
- **Additive observer hook.** `session_decode.py` gains a `diag` object
  (`None` unless `--diag`), constructed in `main()` and threaded into the
  refactored `_run()`. The driver calls three read-only methods behind
  `if diag is not None:` guards — `begin_scan` (after segmentation),
  `on_piece` (at each per-piece terminal: word/tiled, placed, failed,
  in-progress), `end_scan` (after the scan's `decode_tiles`). The hook never
  touches `pds`, so `session_state.pkl` and the fountain result are identical
  with the flag off or on. (The one non-guarded edit renames a colliding
  local `diag` — the fountain diagnostics dict — to `fdiag`.)
- **Headless "live window" = a local web view.** No display and no matplotlib
  in this environment, so a native GUI window is impossible and untestable.
  A `ThreadingHTTPServer` on a daemon thread serves `/` (an auto-refreshing
  HTML page), `/frame.png` (the latest composite, in memory), and
  `/status.json`. This is fully testable headlessly: start the server, GET the
  endpoints, assert the bytes (`tests/test_diag.py`). Frames are also written
  to disk, so a closed/exited run leaves a durable record even after the
  daemon server dies.
- **Cheap per-piece rendering.** The glass base is downsampled once per scan;
  pieces draw onto a persistent overlay (O(sites of this piece), never a full
  re-draw). Panel B's payload-index inverse is cached
  (`draw_decode_map.reassembly_inv`, a factored shared helper) so re-rendering
  it per piece is cheap.

## Geometry (honest note)

A fragment cell `(i, j)` is mapped to glass by scaling the cell grid across the
de-rotated piece rectangle and applying `segment.rotate_transform` (the exact
inverse of the `ndimage.rotate` that de-rotated the piece) plus the piece's
glass bbox origin. The intra-cell grid phase (`dy0/dx0`, < 1 cell) is **not**
threaded out of the sampler; it is dropped. So dots are cell-centre-accurate,
i.e. sub-pixel at the viewer's downsampled scale. This is a **visualization**
(lattice orientation + coverage), not a measurement — the receiver's own
numbers live in the decode log. The tilted box hugs the de-rotated **mask**
bounding box (not the full circumscribing rectangle, which over-covers into
backing).

## Refresh semantics

Panels B and D advance continuously (they read `pds.scans`, which grows per
piece). Panel C (LDPC certification) only advances when the driver runs
`decode_tiles` at a **scan boundary**, so it steps forward at `end_scan`;
running it mid-loop would mutate `pds` and break the byte-identity guarantee.

## Deferred (explicitly out of scope for v1)

- **Per-piece detail inspector** — a side panel with the gate numbers
  (mismatch, z, z-gap, support), pilot/payload BER estimates, window split
  geometry, and refine held-out mismatch for the just-processed piece. The
  hook already receives the placement objects, so this is an additive next
  pass on the same seam.
- Word/tiled pieces show no site dots (their pilots are handled inside
  `formats.page_decode`, not via `fragment_pilot_sites`); they surface in
  panel D instead. Exposing the acquire-internal sampled sites is a later
  extension.
- Keeping the window open after the process exits (a `--diag-hold` blocking
  mode); for now the durable on-disk frames cover post-mortem inspection.

## Regenerating the sample frame

`scratch/diag_probe.py` (session-scoped) drives the viewer over the
`test_session_anchor` canvas and writes `scratch/e018_diag_sample.png`; the
CLI writes the same frames live to `--diag DIR`.
