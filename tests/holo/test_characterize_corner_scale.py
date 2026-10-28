"""W8a — the chiral-corner satellite search must not be seeded from a
threshold-truncated arm.

e031: the Xerox AltaLink B/W discovery sheet printed four perfect corner
marks, but the 300-dpi analysis thumbnail thresholded one arm of two of them
short.  The satellite search radius was seeded per-axis from the component's
own bounding box, so a 36/61.5 wide clip collapsed the x scale to 0.585, the
expected satellite moved inward with it, and the only satellite missed by
5.24 against a 2.25 tolerance.  Both corners were dropped and the page
refused at `corner_registration_failed` — on a physically good print.

The mark is square by construction and the nominal extents already carry the
per-axis sampling DPI, so a per-axis disagreement is truncation, not
anisotropy; thresholding can only shorten an arm, so the longer axis is the
better span estimate.
"""
import numpy as np
import pytest

from holo.characterize.geometry import (
    CORNER_MARK_DOTS, detect_chiral_corners,
)
from holo.characterize.patterns import pattern_bits

# Build at 1:1 layout dots so nominal == CORNER_MARK_DOTS and the numbers in
# the failure messages are directly comparable to the layout.
DPI = 600.0
SIDE = CORNER_MARK_DOTS  # 123
CENTRES = {
    1: (200, 200, (1, 1)),
    2: (700, 200, (1, -1)),
    3: (700, 700, (-1, -1)),
    4: (200, 700, (-1, 1)),
}


def _page(truncate_fraction: float = 0.0) -> np.ndarray:
    """Four chiral corners on white; optionally clip corner 1's right arm.

    `truncate_fraction` erases that fraction of the horizontal arm's right
    half — exactly what a threshold does to a slightly-lighter stroke.
    """
    page = np.ones((900, 900), np.float32)
    for satellites, (cx, cy, inward) in CENTRES.items():
        bits = pattern_bits({
            "kind": "chiral_corner",
            "w_source_dots": SIDE,
            "h_source_dots": SIDE,
            "params": {"satellites": satellites, "inward": list(inward),
                       "stroke_dots": 3},
        })
        y0, x0 = cy - SIDE // 2, cx - SIDE // 2
        patch = page[y0:y0 + SIDE, x0:x0 + SIDE]
        page[y0:y0 + SIDE, x0:x0 + SIDE] = np.where(bits > 0, 0.08, patch)
    if truncate_fraction > 0.0:
        cx, cy, _ = CENTRES[1]
        half = SIDE // 2
        cut = int(round(half * truncate_fraction))
        if cut:
            # whiten the outer end of the right-hand arm only
            page[cy - 3:cy + 4, cx + half - cut:cx + half + 1] = 1.0
    return page


def _detect(page: np.ndarray) -> dict[int, dict]:
    rows = detect_chiral_corners(page, target_dpi=DPI, dpi_x=DPI, dpi_y=DPI)
    return {int(r["satellites"]): r for r in rows}


def test_all_four_corners_on_a_clean_page() -> None:
    found = _detect(_page())
    assert sorted(found) == [1, 2, 3, 4]
    for satellites, row in found.items():
        assert row["crossness"] == pytest.approx(1.0, abs=0.05), satellites


def test_truncated_arm_still_identifies_its_corner() -> None:
    """The W8a regression: a clipped arm must not move the satellite search.

    Seeded per-axis from the bounding box this fails outright — the corner
    is not returned at all, because zero satellites match and the candidate
    is discarded before it can compete.
    """
    clean = _detect(_page())
    cut = _detect(_page(truncate_fraction=0.62))

    assert sorted(cut) == [1, 2, 3, 4], (
        f"truncated arm lost corner(s); got {sorted(cut)}"
    )
    # the fixture must really exercise the defect, or it proves nothing
    x, y, w, h = cut[1]["bbox_thumb"]
    assert w < 0.80 * SIDE, f"fixture did not truncate: bbox width {w}"
    assert h > 0.95 * SIDE, f"fixture clipped the wrong axis: bbox height {h}"

    # identity and position survive the clip
    assert cut[1]["inward"] == clean[1]["inward"]
    assert cut[1]["y_thumb"] == pytest.approx(clean[1]["y_thumb"], abs=1.0)
    assert cut[1]["x_thumb"] == pytest.approx(clean[1]["x_thumb"], abs=1.0)


def test_untruncated_corners_are_unaffected_by_the_clip() -> None:
    """Corners 2-4 must be bit-identical whether or not corner 1 is clipped."""
    clean = _detect(_page())
    cut = _detect(_page(truncate_fraction=0.62))
    for satellites in (2, 3, 4):
        a, b = clean[satellites], cut[satellites]
        assert a["y_thumb"] == b["y_thumb"]
        assert a["x_thumb"] == b["x_thumb"]
        assert a["score"] == b["score"]
        assert a["inward"] == b["inward"]
