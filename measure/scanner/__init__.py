"""measure/scanner — Canon LiDE 400 per-channel optical characterization.

Two instruments, both answering docs/INDEPENDENT-PLANES.md §4.I item 3 /
§6 P2 (= docs/CHARACTERIZE-WORKPLAN.md W11 item 3) from ARCHIVED captures
only — no scan, no print, read-only on every TIFF:

* ``blue_mtf`` — the blue channel of the scanner of record was never
  characterized (e028 measured LUMA from a knife edge, e033 found an R-G
  lateral CA) and the Y plane is read in blue.  Splits scanner optics
  from toner scatter on the e028 pair.
* ``ink_psf`` — E6, 2026-08-23: the same split on the AltaLink e031 pair,
  which has HEALTHY yellow, so "yellow toner scatters" and "that
  cartridge was empty" stop being the same number.  Also carries a
  per-plane registration arm.

    cd <repo>
    PYTHONPATH=measure env/bin/python -m scanner.blue_mtf --all \\
        --evidence-root <evidence> --out build/scanner
    PYTHONPATH=measure env/bin/python -m scanner.ink_psf --all \\
        --evidence-root <evidence> --out build/scanner/e031

Like ``measure/plane_fields``, this is not a test and never runs under
pytest: ``measure/`` is outside ``testpaths`` (user ruling 2026-08-21 —
measurement-instrument code lives in neither ``tests/`` nor ``scratch/``).
Modules import their siblings RELATIVELY, so ``-m scanner.<entry>`` is
the only supported invocation.  Nothing here imports ``holo``; the whole
package is numpy + tifffile + PIL.

* ``_edge`` — the per-channel slanted-edge / line engine (ESF, LSF, MTF,
  and the two channel-ratio differentials that cancel the printed
  target);
* ``_sheet`` — a discovery sheet as an addressable object: page manifest
  + report affine -> any probe's box on any capture of that page, which
  is what lets one code path read two engines' sheets;
* ``_crosses`` — the registration-cross target: reading a 2-dot bar, and
  turning nine of them into a per-plane displacement;
* ``blue_mtf`` / ``ink_psf`` — the two drivers, JSON + figure;
* ``_figures`` — PIL figures (matplotlib is not in this env).

Historical record; the captures are in the evidence archive, joined onto
``--evidence-root`` (``measure/_evidence.py``; ``--selftest`` needs
none).  Artifacts land in the required ``--out``.
"""
