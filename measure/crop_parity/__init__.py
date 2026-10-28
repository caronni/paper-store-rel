"""The holo3 crop parity harness — holo1 vs holo3 on crops, in seconds.

Ported from the holo1-vs-holo2 crop harness in the MAIN worktree
(``holo2/measure/crop_cases.py`` + ``crop_harness*.py``); the holo2 side
is replaced by holo3, and the case source is the holo3 parity record
(``_distill/verify/parity/``) instead of the holo2 differential markdown.

Entry points (all run from the worktree root):

    PYTHONPATH=. env314t/bin/python -m measure.crop_parity.cases --volume e029
    PYTHONPATH=. env314t/bin/python -m measure.crop_parity.harness --volume e029
    PYTHONPATH=. env314t/bin/python -m measure.crop_parity._selfcheck

See ``README.md`` beside this file for the full invocation record.
"""
