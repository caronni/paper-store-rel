"""measure/e045_left_band — the HP M281's left-of-page band per x slice, on scans already on disk (e045).

The question (experiments/045-m281-left-band.md; e044 §044.5): why cmy single-toner cell fields read worse over
x ~4-36 mm (and ~107-135 mm) of the page.  Three readings separated per slice: a registration step (the error
excess goes away at local poses, separation flat), a rendering loss fixed in the print (separation lower, whites
fogged, at every cyan value), the screener (separation lower only where the 212 lpi stipple is zoned).

Modules:
  cells    cells at chosen per-plane poses (window, page affine, sub-window) through one box sampler
  slices   per-slice errors (band / slice colour tables), separation, neighbour model, offsets
  spectra  the screen families per slice
  sheet3   the e043 sheet 3 driver
"""
