"""local_ab — union vs per-origin assembly for the ``tiles.local`` row.

``tiles.local`` assembles ONE attempt out of EVERY lane that covers the
failed tile: `_color_components` builds one `TileCut` per lane and
`tiles.attempt_tile` sums them in `_combine`. That is a union, and the
multi-scan law (CLAUDE.md, F1 o F6) says equal-weight combining can LOSE
to best-single when the errors are correlated. `tiles.retry` does the
opposite: it MIRRORS the failed attempt's origin, so a scan-origin retry
re-attempts one capture alone.

This package measures which is right, on multi-capture material, without
changing anything in ``holo3/``.

    PYTHONPATH=. <python> -m measure.local_ab.cases   --case I-tl
    PYTHONPATH=. <python> -m measure.local_ab.harness --case I-tl

See ``README.md`` beside this file.
"""
