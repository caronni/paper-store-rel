"""Color-uplift campaign harness (PK0) — never pytest-collected.

User ruling, 2026-08-21: *measurement-instrument code must not live in
``tests/`` or ``scratch/``.*  This package was
``tests/holo/_color_uplift_harness/`` until 2026-08-31, where the leading
underscore existed only to dodge pytest collection; ``measure/`` is
outside ``testpaths``, so the underscore is now vestigial and is kept
only so that every ``-m _color_uplift_harness.<module>`` command already
recorded in the campaign record still runs verbatim.  Nothing
here is imported by ``src/holo``; the harness is a pure consumer of the
production receiver seams (RECEIVE-DESIGN v0.50 §6.2a, COLOR-UPLIFT-PLAN
v1.3 §4).

Reproduction commands live in each module's docstring.  Every module runs
as ``python -m`` from the worktree root:

    cd <checkout>
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.<module> --help

Corpus (READ-ONLY, main repo) and run outputs are located by
:mod:`_color_uplift_harness.corpus`.
"""
