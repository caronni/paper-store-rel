"""E9 — LOCAL vs PAGE-GLOBAL detector calibration, as additive attempts.

`docs/TOOLBOX-INVENTORY.md` §6.13 records "local per-state calibration"
as UNMEASURED: named in a brief, with no yield number anywhere in the
record.  This package is the instrument that gives it one, on the K
instance (e029: the M281 c2-r0700 print, Canon 4800 grey, VERIFIED
465,580 B, 1940/1961 tiles, 21 uncertified).

Nothing here is a test and nothing here runs under `pytest`; `measure/`
is outside `testpaths`.  Every module is a READ-ONLY consumer of the
production receiver seams, on the `measure/plane_fields` precedent:
no state is written, no scan is touched, `save_session` is never called.

    cd <checkout>
    PYTHONPATH=src:measure env/bin/python \
        -m calibration.e9_k
"""
