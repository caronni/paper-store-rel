#!/usr/bin/env python3
"""e039 — run `discover analyze` with the corner finder's thumbnail bridged.

On the VersaLink's PDF route the top corner crosses' 3-dot horizontal arms
print as a hatched line (the engine's line screen cuts them into diagonal
dashes); on the 300-dpi corner thumbnail they fall apart into 4-px pieces
with 5-px gaps, the cross is seen as its vertical arm alone and corners 1/2
are refused (039.3t).  This harness wraps `geometry.detect_chiral_corners`:
on its thumbnail only, the dash pieces — dark components at most 2 px tall
and 12 px in area — are widened 3 px left and right and painted dark, so a
hatched arm becomes one line; satellites (4-5 px tall) and everything else
are untouched (a plain 1x7 grey opening also swallowed the satellites into
the crosses: zero corners).  Everything after the corner fit reads the
untouched scan.  DIAGNOSTIC, not the production path — its
reports are not promotable.

    PYTHONPATH=src env/bin/python experiments/039-xerox-versalink/analyze_bridged_corners.py \
        <discover analyze arguments…>
"""
from __future__ import annotations

import sys

import numpy as np
from scipy import ndimage

from holo.characterize import geometry
from holo.cli import main

_original = geometry.detect_chiral_corners


def _bridged(grey, **kwargs):
    image = np.array(grey, dtype=np.float32)
    black = float(image.min())
    threshold = float(np.percentile(image, 90.0)) - 0.42 * (
        float(np.percentile(image, 90.0)) - black
    )
    labels, _ = ndimage.label(image < threshold)
    dashes = np.zeros(image.shape, bool)
    for index, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None or sl[0].stop - sl[0].start > 2:
            continue
        piece = labels[sl] == index
        if piece.sum() <= 12:
            dashes[sl] |= piece
    widened = ndimage.binary_dilation(dashes, structure=np.ones((1, 7), bool))
    image[widened] = black
    return _original(image, **kwargs)


geometry.detect_chiral_corners = _bridged

if __name__ == "__main__":
    sys.exit(main(["discover", "analyze", *sys.argv[1:]]))
