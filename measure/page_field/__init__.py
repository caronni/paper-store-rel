"""measure/page_field — the PAGE-FIELD line's validation harness.

Four tools and one shared module, run from the worktree root, none of
them imported by ``src/holo/receiver``:

* ``extract`` — the reader of PRE-W2 fact snapshots (W2 re-keyed
  ``PlaneField``, so ``snapshot.read`` raises on them).  Written to be
  thrown away at W6 and KEPT there instead: sheet I's snapshot is
  pre-W2 and this is its only reader.
* ``estimate`` — the receiver's OWN collector and solver driven over an
  archived run's placements, certificates and captures: one field per
  (page, plane), the products under ``--out``, and the scheduler-free
  counts B6 asks about.
* ``compare`` — that field against the fits that came before it: the
  analyzer's pooled sheet-H fits, sheet I's supervised sinusoid, and
  the archived per-lane fields ``extract`` kept.
* ``lane_gauge`` — the archived per-lane fields against EACH OTHER,
  which needs no page field and no gauge: the measurement
  ``PAGE-FIELD-DESIGN.md`` §7's footing split rests on since W6
  retracted the cross-gauge one.

    PYTHONPATH=src:. env/bin/python -m measure.page_field.estimate \
        self-check
    PYTHONPATH=src:. env/bin/python -m measure.page_field.estimate \
        run RUN_DIR --out OUT_DIR
    PYTHONPATH=src:. env/bin/python -m measure.page_field.compare \
        --fields OUT_DIR/fields.json --out OUT_DIR/compare.json

``products`` holds what ``estimate`` writes — the records, the tables
and the figures — and ``compare`` and ``lane_gauge`` import it relatively
(one definition of the column profile they score), so this is a real
package and
``-m measure.page_field.<tool>`` is the only supported invocation.  See
``README.md`` beside this file for the inputs, the outputs and the
lead's per-sheet recipes.
"""
