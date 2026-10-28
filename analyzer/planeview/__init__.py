"""planeview — "filter C, treat the whole page as K".

Two doors, both reachable as `python -m analyzer <subcommand>`:

* `emit-plane` (`emit.py`) writes one single-band greyscale TIFF per RGB
  capture of a finished run dir, holding one colour plane unmixed onto
  bright paper / dark ink.
* `plane-view-decode` (`drive.py`) frames that stream's format as a K
  page (`row.py`), replaces six seams of holo3 in-process (`patches.py`)
  and runs the PRODUCTION receiver over the emitted captures.

holo3 is never edited; every deviation is a runtime `setattr` inside the
harness process, listed by file and line in `patches.py`'s docstring and
in `analyzer/PLAN.md` §6.
"""

from __future__ import annotations

from .drive import (DecodePlan, EXPECTED_NO_CLOSE_CODE, build_argv,
                    plan, run)
from .emit import (EmitError, PlaneEmission, emit_capture, emit_run,
                   pixel_affine)
from .patches import Installation, SeamError, install, verify_seams
from .row import (PLANE_OF, PLANE_REF_PREFIX, PlaneRowError, build_plane_row,
                  parse_plane_view_ref, plane_view_ref)

__all__ = [
    "DecodePlan", "EXPECTED_NO_CLOSE_CODE", "EmitError",
    "Installation", "PLANE_OF",
    "PLANE_REF_PREFIX", "PlaneEmission", "PlaneRowError", "SeamError",
    "build_argv", "build_plane_row", "emit_capture", "emit_run", "install",
    "parse_plane_view_ref", "pixel_affine", "plan", "plane_view_ref",
    "run", "verify_seams",
]
