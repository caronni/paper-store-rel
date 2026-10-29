"""Synthetic measurements over the analyzer's decoders.

Not part of the analyzer package's contract: nothing here is imported by
`analyzer.*` modules.  Each sweep is a standalone script that calls the
built modules and writes its results under `--out` (required).  The run
and truth inputs are flags; the dated values each sweep was run on are
recorded in its own docstring, inputs in the evidence archive.
"""
