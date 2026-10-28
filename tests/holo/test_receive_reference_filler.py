"""K-path filler VALUES in the cold reference field.

Every registered K coding has n_filler == 0 and every colour coding takes
the dust branch, so the reference provider's K filler-value arm is dead on
the whole registry.  This exercises it with an off-registry density rung
(HOLO-DESIGN: rungs above the 100-site floor are legal future codings) and
pins the values to the emitter's convention — gen/compose.py draws one flat
(F,) keystream vector per tile at absolute cell addresses.
"""
from __future__ import annotations

import numpy as np

from holo.core import keystream
from holo.format import pilots
from holo.format.descriptor import Coding, FormatSpec
from holo.receive.placement.reference import V1ReferenceField


def _off_registry_spec() -> FormatSpec:
    coding = Coding("c3-r0550-f20-test", cell_dots=3, rate_id="r0550",
                    n_filler=20)
    return FormatSpec(coding, "test-17x17", (17.0, 17.0), 0.0)


def test_k_filler_values_match_emitter_convention() -> None:
    spec = _off_registry_spec()
    tiles_y, tiles_x = spec.layout.tiles_yx
    # A single-tile page masks the defect this test pins (a flat (F,)
    # draw broadcasts into a (1, F) target); the rung must be multi-tile.
    assert tiles_y * tiles_x > 1
    word_cells, filler_cells = pilots.site_cells_yx(
        spec.family_seed, spec.n_filler)
    assert filler_cells.shape == (spec.n_filler, 2)

    provider = V1ReferenceField(spec)
    for page in (0, 1):
        reference = provider.page(page)
        counters = np.arange(tiles_y * tiles_x, dtype=np.int64) + (
            page * tiles_y * tiles_x)
        words = pilots.word_values(spec.seed, counters, spec.plane)
        for index in range(tiles_y * tiles_x):
            ty, tx = divmod(index, tiles_x)
            wy = ty * pilots.TILE_CELLS + word_cells[:, 0]
            wx = tx * pilots.TILE_CELLS + word_cells[:, 1]
            np.testing.assert_array_equal(
                reference.values[wy, wx], words[index])
            fy = ty * pilots.TILE_CELLS + filler_cells[:, 0]
            fx = tx * pilots.TILE_CELLS + filler_cells[:, 1]
            expected = keystream.bits(
                spec.seed, keystream.DOMAIN_FILLER_VALUES,
                spec.plane, page, fy, fx)
            np.testing.assert_array_equal(
                reference.values[fy, fx], expected)
        assert int(reference.sites.sum()) == (
            tiles_y * tiles_x * spec.n_sites)
