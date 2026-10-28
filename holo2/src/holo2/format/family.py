"""``Family`` — the closed set of codec families, and the ONLY dispatch key.

CARRIED VERBATIM (the ten lines of the enum) from
``src/holo/format/profiles.py:32-41``, which FORMAT-SPACE P1 added on
2026-08-19.  Catch-up wave WP-1.1 (2026-08-22): holo2 carries the full
FORMAT-SPACE grammar by the user's ruling, so all three families are
frozen here now even though holo2 decodes only K — the colour port needs
the enum to exist before it can name a row, and a value invented later
would be a fork.

**The string values are format-frozen.**  They are the evidence-block
kinds of the durable record (``holo/receive/evidence_blocks.py:33-42``:
magics ``holo/e023b/evidence-block/{cmy7,cmy8}-v1``, arities k=1 /
cmy7=6 / cmy8=3).  That alignment is why the origin's conversion needed
no state rewrite — the persisted record already spoke ``"k"``/``"cmy7"``/
``"cmy8"``, so ``expected_kind = spec.codec_family.value`` is total and a
four-branch chain plus its ``None``-refusal was deleted outright
(``holo/receive/_runtime_validation.py:168``).  Renaming a value is a
printed-format fork, never a refactor.

**Family is the only legal dispatch key** (FORMAT-SPACE §2 and
``docs/FORMAT-SPACE-DISPATCH.md``, "Retired dispatch forms"): never
object identity against a profile singleton, never a ``codec_id`` string
compare, never an id substring.  ``codec_id`` is an informative label —
in the v2 identity space it is not even unique (every K row reports
``"k-v1"``).  The origin measured the cost of the alternative: an
identity compare handed a freshly built ``-x1`` colour row the **K**
reference field — no dust — silently, and the dispatch table annotates
that site "the c4-row branch bug site, now unrepresentable".

This module is the BOTTOM of ``format``'s dependency order: it imports
no sibling module (only ``enum``), so ``close_spec``, ``format_v1`` and
``registry_rows`` may each name a family without a cycle.
"""
from __future__ import annotations

import enum


class Family(str, enum.Enum):
    """The closed set of codec families (FORMAT-SPACE §5).

    The string values are format-frozen: they are the evidence-block
    kinds of the durable record (``receive/evidence_blocks.py``).
    """

    K = "k"
    CMY7 = "cmy7"
    CMY8 = "cmy8"


__all__ = ["Family"]
