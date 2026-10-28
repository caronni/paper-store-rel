# measure/calibration — the detector-calibration locality instruments

**Nothing here is a test and nothing here runs under `pytest`.**
`measure/` is outside `testpaths`; these entry points open archived
states, stream a 2.29 GB scan, and take minutes. This package is the
sibling of `measure/plane_fields`, on the same rules: READ-ONLY
consumers of the production receiver seams, no state written, no
`save_session`, no `src/holo` import of anything here.

Line docs: `docs/TOOLBOX-INVENTORY.md` §6.13 (the E9 entry) and
`docs/INDEPENDENT-PLANES.md` §2.13 (the measurement record).

## How to run anything here

`measure` goes on the path, `calibration` is the package, and every
module imports its siblings **relatively** — so `-m calibration.<entry>`
is the only supported invocation:

```
cd <repo>           # or a worktree
PYTHONPATH=src:measure env/bin/python \
    -m calibration.e9_k
```

## The instrument

### `e9_k` — E9, K instance: LOCAL vs PAGE-GLOBAL calibration

**Subject.** e029, the first physical holo-v1 print: `c2-r0700@3392x2368`
on the HP CLJ M281fdw at the `hp-m281-ink` 4.5 mm geometry, one Canon
4800 dpi grey scan, closed **VERIFIED** at 465,580 bytes with
**1940/1961** tiles certified. The residue is the complete set of **21**
uncertified tiles, whose geography the e029 log attributes to HP weak
horizontal development banding plus the two extreme columns — i.e. to
UNEVEN TONER, which is exactly the premise a local calibration is
supposed to exploit.

**Inputs, all read-only and sha-checked**

| file | sha256 |
|---|---|
| `scratch/e028/holo-c2-r0700-q07-ink-counting/receive.state` | `bdd7b293…` (8.2 MB) |
| `scratch/e028/hp-canon-c2-ink-counting.tiff` | `d9c4e932…` (2.29 GB) |
| `…/page000_gt.npy` | `3e485603…` (the emitted DOT raster) |
| `…/payload-counting.bin` | `e5021f8d…` |

**The truth path is validated before it is used.** The GT sidecar is
compared cell for cell against `records.printed_cells_from_record` on all
1940 certificates — 7,946,240 cells, 0 mismatches — so the residue's BER
is measured against a truth the receiver's own certificates corroborate.

**The pipeline is production, not a re-implementation.** Per ladder lane:
`place.place_committed` re-derives the archived poses (the R-level
inventory), `payload.collect_capture_evidence` samples and calibrates,
`_payload_context.apply_region_context` fits and gates the context arm,
`payload.freeze_capture_evidence` picks owners, `blocks_from_frontier`
materializes tile blocks and `payload.attempt_k_tile` runs the ordinary
certificate gate at both K stages.

**The reproduction control.** Arm R is the incumbent recipe expressed in
the instrument's own vocabulary. Its blocks come out **bit-identical to
the archived evidence** on every residue tile at every lane measured
(l00 72,158/72,158 · l01 74,664/74,664 · and, in the prototype, l02
73,795/73,795 and l03 78,726/78,726). Nothing in the arm table can be an
artifact of the harness.

**The arms** — each changes exactly ONE thing, the label population the
per-window marginal PAVA is fitted on:

| arm | scope | labels |
|---|---|---|
| `R` | this window | format-known (BCH word) cells only — production |
| `W` | this window | + this window's certified payload cells |
| `H1` | + 1 window-extent halo | same |
| `H2` | + 2 window-extent halos | same |
| `G` | every window of the lane | same |

`W` vs `R` isolates *do certified labels help?*; `H1/H2/G` vs `W`
isolates *does a WIDER population help?*; `G` vs `H2` is the locality
question itself.

**One declared deviation.** A `pava-v1` map's LLR bound is
`log(n_fit + 1)`. Production fits ~490 labels per window, so that bound
is ~6.2 and sits far inside the receiver's registered emitted clamp
`detect.CTX_LLR_CLAMP = 12`. A certified-label population is 10^4–10^6
wide, its bound passes 12, and `WindowEvidence` then refuses the row for
any cell with no valid context neighbourhood (`apply_context_offsets`
clamps only the cells it corrects). The instrument therefore clamps the
fitted probability NODES to the range that clamp implies, once, at the
fit. It is an exact no-op for arm R — proven by the bit-exactness above
— and conservative elsewhere.

**Memory.** With the native capture released after decimation, one lane
costs, peak RSS: **3.5 GB at 2 ppc, 4.6 GB at 4 ppc, ~12 GB at 8 ppc,
31 GB at 16 ppc**, because `placement.geometry.prepare_region`
materializes five region-sized float32 arrays. The default lane set is
`l00-2ppc-600dpi,l01-4ppc-1200dpi`; pass `--lanes` to add the finer ones
when the budget allows.

**Outputs** (`scratch/plane-fields/p2/e9/`): `e9-k-raw.json` (everything,
including the page-wide per-tile BER of every arm), `e9-k.json` (the
reduction), `e9-k-<lane>.png` (page BER map + arm delta map + the
complete residue table + the fitted-threshold field), `README` notes
here, and the record in `docs/INDEPENDENT-PLANES.md` §2.13.
