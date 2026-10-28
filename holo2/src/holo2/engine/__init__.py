"""engine — scheduling: session lineage, recipe, orchestrator.

Imports ``core`` only (including the work protocol). The engine knows
protocols, gates, routes and prices — never a concrete solver, a format
leaf or a pixel reader. R1 finished that job for the orchestrator (it
enumerates PROVIDERS, and asks its own ``CloseConsult`` — the terminal
consumer that used to be dressed as a third provider, worklist B12);
R2 finished it for the session: ``runtime`` is gone, and what it owned that the engine may
not name — the printed row, ingest, window lattices, the derived views —
went to ``format``, ``capture`` and ``solve``. What is left arrives as a
:class:`Plane`, built by the composition root, whose every member is a
core type or JSON.

The engine's layering debt is therefore empty (``tests/test_layering.py``).

**RECORDS engine owns** (R3, ``records.py``): ``SessionIdentity`` (v1) —
the envelope header, written by :func:`open_session` when a run names its
lineage. It is the registry's one ``kind=None`` family: it has no
resource key, and the store decodes ``envelope["session"]`` through it.
The engine names no other record type anywhere — what it reads off the
plane is core types or JSON.

**Error taxonomy** (R1): ``FireCountTripwire`` and ``NoProviderError`` are
the engine's exceptions, and since B4 neither is on the surface — both
are raised and handled inside the engine, and a declared type with no
cross-package handler is API kept alive by its own pin. Cross-package
code here catches core's, nothing else.
"""
from __future__ import annotations

from .orchestrator import Orchestrator, RunOutcome
from .recipe import RECIPE_V1, Recipe
from .records import RECORD_FAMILIES, SessionIdentity
from .session import POLICY_ID, Plane, SessionContext, open_session

__all__ = [
    # B4 cut this list to what the tree consumes. ``RecipeEntry`` builds
    # a ``Recipe`` and only the recipe crosses; ``PlaneFactory`` is
    # ``open_session``'s own parameter type; ``FireCountTripwire`` and
    # ``NoProviderError`` are raised and handled inside the engine, so
    # neither is a declared cross-package catch. All four stay importable
    # from their modules and rejoin this list in the diff that first
    # imports one from another package.
    "Orchestrator", "POLICY_ID",
    "Plane", "RECIPE_V1", "RECORD_FAMILIES", "Recipe",
    "RunOutcome", "SessionContext", "SessionIdentity",
    "open_session",
]
