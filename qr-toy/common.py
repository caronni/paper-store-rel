"""Fixed, deliberately out-of-band interpretation for the single-tile toy."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
from holo.format.descriptor import FormatSpec
from holo.format.resolve import resolve_format_ref
from holo.receiver.format import identity
from holo.receiver.plugins import calibrate

FORMAT = "1i40-k-r0547-p103@1x1"
PAYLOAD_BYTES = 263
CELL_MM = 25.4 / 40
TILE_MM = 64 * CELL_MM


def format_parts() -> tuple[
    FormatSpec, identity.FormatRow, identity.SiteGeometry, np.ndarray, np.ndarray
]:
    """Resolve the shared generator/receiver contract and its known cells."""
    spec = resolve_format_ref(FORMAT)
    row = identity.resolve_format_ref(FORMAT)
    geometry = identity.build_site_geometry(row)
    cells = np.indices((64, 64)).reshape(2, -1).T
    lookup = calibrate.build_site_lookup(geometry)
    reference = calibrate.format_reference_values(row, lookup, 0, cells)
    assert spec.symbol_bits == PAYLOAD_BYTES * 8
    assert np.count_nonzero(reference >= 0) == 103
    return spec, row, geometry, cells, reference
