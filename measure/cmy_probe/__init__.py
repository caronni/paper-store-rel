"""measure/cmy_probe — the readout and its synthetic self-check for the E043 M281 cmy probe sheet.

The sheet and its questions: docs/CMY-PROBE-M281.md (v0.2) §2 (the arms: five c2 cell bands, the colour-point
bars, the controls) and §4 (readout and decision).  The emitter is experiments/043-m281-cmy-probe/; this
package reads what it printed, from its manifest and ground-truth npz, never from a regenerated raster.

Modules:
  readout   scan(s) + manifest + GT npz -> bars.csv, bands.csv, bands_profile.csv/.svg, edges.json, summary.json (+ bar spectra PNGs);
            the e041 methods (fiducial page fit, per-plane poses, the known-lattice bar score) imported from
            measure/e041_*.py, which import cleanly (their argument parsers live in main())
  bars      per bar the verdict (the whitened whole-bar families, clean / marginal / screened against the
            sheet's white bars; the e041 lattice score kept as legacy), ladders, edges, rgb_solid
  bands     the cell bands (c2 or c3): hard cell error at per-plane poses, offsets
  stipples  the whitened whole-patch spectra at the engine's five screen families (THE verdict's instrument)
  series    the three named ratios per toner: series, the magenta grid, the proposed value per toner
  checkerboards  sheet 2's pairwise checkerboards: dot gain, edge width, plane offset, families off the pattern
  dots      sheet 2's dot-level set: on / off contrast per pattern
  tables    the CSV tables and table lines
  profile   the per-band x-profile of the in-band lattice score (screening over SOME of a band's x extent)
  patches   the plateau-edge patch sheet (legacy scores)
  synth     a seeded synthetic 2400 dpi scan of the manifest's sheet with planted plateau edges, screens and
            cross-talk; runs the readout on it and asserts the recovery (the self-check before any scan);
            synth_sheet2 its sheet-2 case (planted checkerboards and dots)

    PYTHONPATH=src:. env/bin/python -m measure.cmy_probe.synth --out <dir> [--manifest M --gt G] [--seed N]
    PYTHONPATH=src:. env/bin/python -m measure.cmy_probe.readout --scan S.tiff --manifest M --gt G --out <dir>
"""
