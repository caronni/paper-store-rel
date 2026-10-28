"""Color furniture projected onto the binary E021/E022 luma footing."""
from __future__ import annotations

import numpy as np
import pytest

from holo.format import pilots
from holo.format.registry import get_format_row
from holo.receive.placement.reference import V1ReferenceField


@pytest.mark.parametrize(
    "row_id",
    (
        "c2-cmy7-p120-v0@3328x2304",
        "c3-cmy7-p120-v0@2240x1536",
        "c2-cmy8-p120-v0@3328x2304",
        "c3-cmy8-p120-v0@2240x1536",
    ),
)
def test_color_reference_matches_ideal_equal_channel_luma_split(
    row_id: str,
) -> None:
    spec = get_format_row(row_id)
    reference = V1ReferenceField(spec).page(0)
    word_cells, dust_cells = pilots.color_site_cells_yx(
        spec.family_seed)
    expected_word = pilots.word_values(
        spec.seed, (0,), pilots.PLANE_K)[0]
    states = pilots.dust_state_values(
        spec.seed, (0,), spec.codec)[0]
    ink_count = np.asarray((0, 1, 1, 2, 1, 2, 2, 3), np.uint8)
    expected_dust = (ink_count[states] >= 2).astype(np.uint8)

    np.testing.assert_array_equal(
        reference.values[word_cells[:, 0], word_cells[:, 1]],
        expected_word,
    )
    np.testing.assert_array_equal(
        reference.values[dust_cells[:, 0], dust_cells[:, 1]],
        expected_dust,
    )
    assert int(reference.sites.sum()) == (
        spec.tiles_per_page * 120)
