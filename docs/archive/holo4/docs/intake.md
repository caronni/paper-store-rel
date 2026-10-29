# intake

Physical evidence in. The run's first truth plane.

## What it is

The conversion of operator-supplied scans into authenticated, comparable
rasters the rest of the machine may read:

- SHA-256 of the file bytes is the capture identity. Duplicate SHAs
  fold; they are not two captures.
- DPI is operator-declared. The machine does not invent it. A
  misdeclared DPI is a clean refusal (e033), not a resample.
- Native raster → per-plane u8 `.npy` on disk, once. Workers mmap
  their own read-only views (free-threading: no shared-object
  refcount fight).
- Exact-area integer-box decimation to a ppc ladder ending at native.
  Never resize-from-resize. Never submit an externally decimated view
  as a second capture.
- Colour: RGB mean then box (E018 order). Luma-then-decimate is
  forbidden — it shifts phase.
- Grey vs RGB is a property of the file. A grey capture can place
  (W/CM projected to luma) and cannot mint a colour certificate.
- Platen backing (median border luma) is measured here, used later as
  a photometric nuisance, not as a detector.

This is the domain CHARTER called "thin but load-bearing." Silent
harvest forks live here more often than in LDPC.

## What it is not

- Survey. Finding *where* paper is, and voting pitch, is a plugin
  (core row). Intake does not read pilots and does not invent
  regions.
- A capture of a capture. Derived views of one SHA are footings of
  that SHA. They are never independent evidence and they are never
  summed.
- Format. Pitch *class* is format; pixels-per-cell of *this scan* is
  `dpi × pitch_in`.

## Laws (physical evidence)

- One ordinary state freezes one DPI. Mixing grey and colour modes
  for absolute y is poison (home flatbed).
- Combining LLRs is legal only across independently acquired SHAs,
  already bounded and calibrated, same footing class.
- Block-coded (JPEG) members change detector choice; they do not
  become extra captures.
- The run dir's plane cache is disposable. Identity is the SHA, not
  the `.npy` path.

## Seams

intake → data (`Capture`, `Level`, `PlaneRaster` are frozen inputs).
intake → survey (the first plugin that reads rasters).
intake ↛ close, ↛ certificates.

In holo3, intake is a function the engine calls before the descriptor
loop, not a priced row. That is the right shape: there is nothing to
wake. Do not make it a plugin so it "looks regular."

## holo4 stance

Keep this small and named. A 50-line module with the SHA/DPI/ladder
laws written as types (`Capture` cannot exist without a SHA and a
declared DPI) beats a 400-line "loader" that also surveys. When
someone wants to pass `--dpi` twice for the same file, refuse here.
