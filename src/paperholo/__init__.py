"""paperholo — fiducial-free holographic data storage on laser-printed paper.

Modules mirror docs/DESIGN.md: channel (§3), modulation (§4), pilots+sync (§5),
inner FEC (§6, TODO M2), outer fountain (§7, TODO M3).
"""
__version__ = "0.0.1"

# NOTE: paperholo.encodings (the L1-encode/L0-emit seam: registry + emitter +
# `python -m paperholo.encodings` CLI) is deliberately NOT imported eagerly —
# an eager import here makes runpy warn about double-import on every CLI
# invocation. Import it explicitly: `import paperholo.encodings`.
