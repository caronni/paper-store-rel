"""measure/mic_discovery — the yellow tracking dots (MIC) and the HCAL
self-report strip of one colour discovery capture.

Owner's ruling D5 (2026-10-09): measured on the COLOUR HCAL DISCOVERY
captures only, never on payload sheets.  ``capture`` reads the TIFF once
(memory-mapped, banded) into the yellow plane's dot candidates and a
blank-paper map; ``lattice`` finds the dot lattice, indexes the dots,
finds the payload repeat and folds it into one cell; ``docucolor``
tries the 2005 Xerox DocuColor reading on that cell; ``strip`` reads the
self-report with the characterize instrument's own decoder; ``render``
draws the cell and a 1:1 crop.  README.md carries the method and the
per-engine results.
"""
