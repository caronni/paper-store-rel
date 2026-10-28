"""PLANE-FIELDS instruments — the W0/V0, W6, swim and GT-affine drivers.

Never pytest-collected: ``measure/`` is outside ``testpaths`` (the
``holo2/measure`` precedent, user ruling 2026-08-21 — measurement-
instrument code lives in neither ``tests/`` nor ``scratch/``).  Nothing
here is imported by ``src/holo``: these are READ-ONLY consumers of the
production receiver seams (docs/PLANE-FIELDS.md §6.2 W0), in the
``_color_uplift_harness`` mould.

    cd <repo>          # or a plane-fields worktree
    PYTHONPATH=src:measure env/bin/python \
        -m plane_fields.field_from_certs --help

``measure`` on the path, ``plane_fields`` the package: every module
inside imports its siblings RELATIVELY, so ``-m plane_fields.<entry>``
is the only supported invocation (a by-path run cannot resolve them).

Four instruments live here — see README.md for inputs, outputs and the
recorded caveats:

* ``field_from_certs`` — the W0/V0 per-plane field from certificates
  alone, plus ``qualify_sheet_i`` (the W6 dial-ON qualification);
* ``swim_pilot`` — the §6.5.5a SWIM CHARTER feasibility pilot
  (``_swim_inputs`` state/scan access, ``_swim_setup`` targets and
  committed geometry, ``_swim_probes`` the two NCC estimators,
  ``_swim_region`` the per-candidate decode driver, ``_swim_truth`` the
  ground truth from the closed volume, ``_swim_figures``), which drives
  the production decode leaves at
  candidate per-plane sampling offsets and accepts on the ORDINARY
  certificate gate;
* ``gt_affine`` — the SUPERVISED AFFINE CEILING (``_affine_fit`` the
  sampler/fit/statistics engine, ``_gt_affine_run`` the driver), which
  fits a full 6-dof per-plane sampling affine against the printed truth
  the closed volume supplies and reports what error survives it, so the
  swim's ~10% floor can be split between unmodelled geometry, photometry
  and irreducible noise; and
* ``extract_panels`` → ``render_panels`` — the two-stage dead-vs-GT
  figure pipeline over one ``gt_affine`` result file.

None of them ever writes to a state or a scan, and none calls
``save_session``.  Every artifact they write lands under
``scratch/plane-fields/``.
"""
