"""Standalone printer/scanner discovery and calibration instrument.

The package is intentionally outside the production generator and receiver.
It emits scratch sheets and measures their known stimuli; it never supplies a
numerical path to archive generation or recovery.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "2"
