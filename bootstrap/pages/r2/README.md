# pages/r2/ — records of the R2 pages (R2-FORMAT v1, 2026-10-20)

Written by `python3 bootstrap/build.py --record` (a run without it writes
under bootstrap/build/build-py/ only, its r2/ there; since 2026-10-23 both
build today's chain, which is not the 10-20 print). The page bitmaps, grids
and camera renders are not in git (derived output, the repo rule): build.py
regenerated them byte-identically into `bootstrap/build/r2/` (gitignored, the
10-20 record; build.py's own root is build/build-py/ since 2026-10-23), and
`SHA256SUMS` here pinned every one of them.

- `bundle.bin` — `build/bundle/b.py`, the one Python file the pages carry:
  a module docstring holding the text of R2-FORMAT.md, then the full text of
  `r2reader/reader.py` (shared region included). A STAND-IN content: the
  design's R2 payload is the R3 reader + the R3 spec, which do not exist yet
  (RECORD-2026-10-20, ruling 8).
- `payload.bin` — the pages' data: cm2 v2 (the big-integer rANS coder,
  `typed/cm2_enc.py`, orders read from `typed/cm2_dec.py`) of bundle.bin
  with primer `build/loader/r.py` (what a.py writes, in binary: its
  definitions + the stage-2 reader) — the coder state x as big-endian
  bytes. No length prefix: the header in every bullseye block carries the
  length and the CRC-32.
- `payload.json` — sizes, pages, capacity and headroom, chunks per page,
  fourth copies, white slots, and the hashes of payload, bundle and primer.
- `page_p{P}.json` — `r2/gen.py`'s sidecar of page P: geometry, header,
  bullseyes, slot → chunk, copies, the designed placement (PI1, PI2, SKIP, OVERFLOW).
- `page_p{P}.<capture>.json` — `r2/camera.py`'s truth sidecars of the base
  captures (flatbed300, nominal-b030, nominal-b045, hard-b030): parameters,
  seed, homographies.
- `SHA256SUMS` — `build/r2/SHA256SUMS`: every file build.py writes under
  build/r2/ (bitmaps, grids, renders with their truth sidecars, payload,
  verify_grid's report, reads.json / reads.md).

The stage-2 reader of this build is the one build.py was given (`--reader`;
default the readable `r2reader/reader.py`, standing in until the diet reader
lands); the primer, and so payload.bin, change with it.

The v0 records (page_10x3, page_12x2 and the 4-byte-length payload of
2026-10-18) are in git history up to 33736db8; R2-FORMAT v1's gen.py no
longer makes those pages.
