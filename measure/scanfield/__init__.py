"""measure/scanfield — is the scanner's own per-channel geometry worth
compensating for a colour decode?

One instrument, ``channel_ca``, answering one question with a number:

    across the platen, how far apart do R, G and B put the same physical
    mark, in 600-dpi printed dots, and does that reach the field
    service's 0.25-dot publish floor (``src/holo/receiver/plugins/fields.py``
    ``MIN_DELTA_DOTS``) anywhere a payload region sits?

    cd <repo>
    PYTHONPATH=measure env/bin/python -m scanfield.channel_ca --all \\
        --evidence-root <evidence> --out build/scanfield

``measure/scanner`` is the neighbour and the dependency: its
slanted-edge engine (``scanner/_edge``) and its manifest-driven target
locator (``scanner/_sheet``) are reused unchanged, so the two
instruments cannot drift apart on the shared physics.  What is new here
is the QUESTION — ``scanner`` asked how sharp each channel is and
sampled x 35-155 mm; this asks where each channel PUTS things, and has
to reach the outer platen, because that is where a lens' lateral
chromatic aberration would live.

* ``_marks``   — per-channel first moment of a small achromatic mark,
                 plus its synthetic injected-truth calibration;
* ``_targets`` — which black things on the HCAL-R1 discovery page to
                 read, located through the page manifest;
* ``_margin``  — the confetti-field boundary of a real payload sheet, an
                 upper bound (scanner + printer, not separable);
* ``_figure``  — the offset map, four panels on one axis (PIL, reusing
                 ``scanner/_figures.Panel``);
* ``channel_ca`` — the driver, the aggregation and the verdict.

Like ``measure/scanner`` and ``measure/plane_fields`` this is not a test
and never runs under pytest (``measure/`` is outside ``testpaths``; user
ruling 2026-08-21 — instrument code lives in neither ``tests/`` nor
``scratch/``).  Modules import their siblings relatively, so
``-m scanfield.<entry>`` is the only supported invocation.  Nothing here
imports ``holo``, ``holo2`` or ``holo3``: numpy + tifffile.

Read-only on every capture — no scan, no print, no decode.  Historical
record; the captures are in the evidence archive (``--evidence-root``,
``measure/_evidence.py``).  Artefacts land in the required ``--out``.
"""
