"""diag — the observer: status service, panes, published artifacts.

diag reads anything and is read by nothing but the composition root
(``cli``). It is strictly downstream and strictly optional to a run: a
port that will not bind prints one line and the decode proceeds untouched
(DESIGN L12). Nothing here may write durable state.

``panes`` is imported by ``status`` (Pillow is a hard dependency, not an
optional one: a tree without it fails at import rather than degrading to
a silently pane-less observer). It is not re-exported here — tests and
the panes renderer import ``holo2.diag.panes`` directly.
"""
from __future__ import annotations

from .status import StatusProvider, finalize, serve

__all__ = ["StatusProvider", "finalize", "serve"]
