# e043 — the M281 cmy emission probe sheet

The generator of docs/CMY-PROBE-M281.md (v0.2) §2–§3: one plain PostScript
job (PSDoc, no PJL) with five c2 cell bands (M-hex, M-a85, I-2, I-8, I-ref),
the device-RGB ladder bars, the registry values in every construct, and the
white / scrambled / screened controls. The record is
`experiments/043-m281-cmy-probe.md` (opened on print day).

Regenerate (byte-identical; seeds 43 cells, 44 layout) and run the gs gate,
from the repository root:

    PYTHONPATH=src env/bin/python experiments/043-m281-cmy-probe/probe_sheet.py \
        --out build/e043 --check

Outputs — `E043-m281-cmy-probe.ps`, `.manifest.json`, `-gt.npz` — are
derived and NOT committed (`/build/` and `experiments/*/build/` are
gitignored); the job's sha256 and byte count go in the log. Printing is the
owner's, via `scripts/print_plane.sh`, only on his go.


## After the read (2026-10-11)

The sheet printed (page 3410) and was read the same day; the log
`experiments/043-m281-cmy-probe.md` holds three readings (043.3, 043.3b,
043.3c — the last is the one that stands) and the owner's own eye
findings (043.4). The instruments that read it live in `measure/cmy_probe/`:
`readout.py` (fiducial fit, bands, bars), `bars.py`, `bands.py`,
`profile.py` (the in-band x profile), `patches.py` (the plateau-edge patch
sheet), `stipples.py` (the whitened whole-patch spectra at the engine's
five screen families — the verdict that stands), `synth.py` (the seeded
self-check). The screening-along-x question was answered with e041's own
`measure/e041_band_screen.py`. Sheet 2 is specified in
`docs/CMY-PROBE-M281.md` §9 and emitted by `probe_sheet2.py` (built after
this note).

## Sheet 2 (E043b, the same day)

`probe_sheet2.py` emits it from the registry's `hp-m281` values (sheet 1
regenerates byte-identically with `probe_sheet.py --lookup legacy-e043a`):

    PYTHONPATH=src env/bin/python experiments/043-m281-cmy-probe/probe_sheet2.py \
        --out build/e043b --check

Six bands (c2 in four constructs, c3 in two), twelve pairwise cell
checkerboards, 85 bars (the cyan G series, the magenta R × B grid, the
yellow corner, both constructs; the registry triples as I-8 and I-ref;
white / scrambled / screened controls), fifteen dot-level patches. The
readout is the same `measure/cmy_probe/readout.py`, which reads the extra
sections when the manifest carries them: `series.py` (ratio series, the
magenta grid as a table, the proposal — the registry value stands when
clean), `checkerboards.py` (ink fraction by a per-pixel Neugebauer–Demichel
unmix, 10–90 % edge width, plane offsets from the diagonal fundamentals,
families off the pattern's harmonics, a composite PNG per pitch), `dots.py`
(depth of the marks against the sheet's solids, a zoom PNG per toner),
`tables.py` (the CSVs), `specks.py` (sparse foreign dots per
mm² in each ink density — the owner's "C mottling", a `speckled` verdict
the families cannot give), `synth_sheet2.py` (`synth.py --case sheet2`, the
self-check with planted gain, offsets and a stipple). The band families
exclude the cell lattice's own harmonics (a c3 field's 200 lpi line sits in
the 196 lpi family). The record is §043.5 of the log; the refuter's
findings on the first run and their dispositions are listed there.

Artefact homes (2026-10-11 night): the three printed jobs with their
manifests and GT are copied to `scratch2/e043/jobs/`, `scratch2/e043b/jobs/`
and `scratch2/e043c/jobs/` beside each sheet's readouts; the scans sit in
`scratch2/` as `E043-m281-cmy-probe{,2,3}-a-scan.tiff`.
