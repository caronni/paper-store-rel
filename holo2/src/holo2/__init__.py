"""holo2 — receiver restart (design phase; see holo2/docs/DESIGN.md).

Receiver-only. Decodes printed format v1 (generation stays in
``src/holo``). Firewall: nothing in this package imports ``holo`` or
``paperholo``; carried leaves are copied and adapted, with equivalence
pinned by oracle tests outside this tree (``tests/holo2_oracles/``).

Status: PROVISIONAL by construction until a recorded qualification and
a user adoption ruling (DESIGN.md L15).
"""

__all__: list[str] = []
