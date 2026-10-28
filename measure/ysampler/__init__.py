"""Y-anchor sampler instruments — the ink-free anchor supply measurement.

**src/holo diff: zero.**  The ink-free anchor kernel measured here is
composed at RUNTIME from production's own parts
(:mod:`ysampler.composition`) and exists only inside this process.
Standing rule from the project lead (2026-08-30): *v1 measurement needs
are met by runtime composition inside a harness, never by tree edits.*

Never pytest-collected: ``measure/`` is outside ``testpaths`` (user
ruling 2026-08-21 — measurement-instrument code lives in neither
``tests/`` nor ``scratch/``).  Nothing here is imported by ``src/holo``;
every module is a READ-ONLY consumer of the production receiver seams,
in the ``_color_uplift_harness`` mould.

    cd <repo>          # or a ysampler worktree
    PYTHONPATH=src:measure env/bin/python \
        -m ysampler.anchor_supply --name frozen-cmy7

Line record: docs/COLOR-UPLIFT-MEASUREMENTS.md §15 (the PK6/A2
measured negative) — closing finding 4, "Y anchors are not currently
measurable at fine pitch (dust-only supply …) — a sampler improvement
… is prerequisite to ANY Y-side registration claim".  See README.md.
"""

# The roots this package's DOCUMENTED run line puts on sys.path, stated
# by the producer rather than inferred downstream.  ``ysampler.composition``
# needs ``src`` only; ``ysampler.anchor_supply`` additionally imports
# ``_color_uplift_harness.{patch_corpus,patch_runner}`` to drive the one
# bounded specimen decode it spies on -- a tracked in-repo package which,
# since 2026-08-31, lives beside this one under ``measure/`` and so needs
# no root of its own.
#
# FORWARD DECLARATION: nothing in the tree reads this today.  It is a
# statement of fact for whoever wires an import-hygiene reader, not a
# gate contract, and satisfies no gate on its own.
IMPORT_ROOTS = ("src", "measure")
