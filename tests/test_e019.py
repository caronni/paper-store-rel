"""exp-019 preflight: the lattice-candidate acquisition stage
(segment.find_lattice_candidates) + the segment_pieces receiver-revert."""
import inspect
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/019-platen-segment"))

from paperholo import segment                       # noqa: E402
import gen_platen_fixture as G                        # noqa: E402
import qualify_e019 as Q                              # noqa: E402


def _fixture(seed=19, backing=40.0):
    return G.build(dpi=1600, width_mm=45, backing=backing, seed=seed,
                   blur=2.0, noise=7.0, schedule=G.SMALL_SCHEDULE,
                   gap_mm=5, border_mm=4)


def _cands(canvas, **kw):
    return segment.find_lattice_candidates(canvas.astype(np.float32),
                                           cell_px=8.0, dpi=1600.0, **kw)


def test_fixture_deterministic():
    a, gta = _fixture()
    b, gtb = _fixture()
    assert np.array_equal(a, b) and gta == gtb and len(gta) == 3


def test_finds_data_fields_not_margin():
    canvas, gt = _fixture()
    im = canvas.astype(np.float32)
    cands = _cands(canvas)
    assert len(cands) == 3            # one candidate per scrap, no ring/split
    for c in cands:
        y0, x0, h, w = c.bbox
        masked = im[y0:y0 + h, x0:x0 + w][c.mask]
        assert masked.mean() < 186    # a DATA field (~147), not white margin (225)
        assert masked.std() > 20      # modulated, not flat
    # GT anchor: total masked area tracks the FIELDS, well below the SCRAPS —
    # would fail if the detector engulfed the white margins (a real regression).
    scrap_mm2 = sum(g["size_mm"] ** 2 for g in gt)
    assert sum(c.area_mm2 for c in cands) < 0.85 * scrap_mm2


def test_backing_agnostic():
    # WHITE backing: margin is white-on-white, invisible to |mean-backing|;
    # modulation still finds the fields (never reads `backing`).
    assert len(_cands(_fixture(backing=250.0)[0])) == 3


def test_sub_grain_flag():
    cands = _cands(_fixture()[0])
    subs = [c for c in cands if c.sub_grain]
    bigs = [c for c in cands if not c.sub_grain]
    # SMALL_SCHEDULE = the two 12 mm fields + one 8 mm/2 mm-margin (4 mm field).
    # The flag must pick out ONLY the small field, not tautologically restate it.
    assert len(subs) == 1 and len(bigs) == 2
    assert all(c.area_mm2 > 100.0 for c in bigs)          # the two 12 mm fields
    assert subs[0].area_mm2 < min(c.area_mm2 for c in bigs)


def test_interior_blank_does_not_fragment_or_get_claimed():
    # an enclosed blank hole (data-ABSENT) must NOT split the field into two
    # candidates (connectivity holds it together) and must NOT be claimed as
    # lattice (no fill_holes — a hole is an honest erasure, not payload).
    img, _ = Q.make_case(np.random.default_rng(1), "quiet")
    cands = segment.find_lattice_candidates(img, cell_px=24.0, dpi=4800.0)
    assert len(cands) == 1                                 # not fragmented
    filled = ndimage.binary_fill_holes(cands[0].mask)
    assert cands[0].mask.sum() < 0.97 * filled.sum()       # blank stays a hole


def test_torn_shape_is_followed_not_bboxed():
    img, _ = Q.make_case(np.random.default_rng(2), "torn")
    cands = segment.find_lattice_candidates(img, cell_px=24.0, dpi=4800.0)
    assert len(cands) == 1
    y0, x0, h, w = cands[0].bbox
    bbox_cells = (h // 24) * (w // 24)
    assert cands[0].n_cells < 0.90 * bbox_cells    # follows the cut, not the box


def test_multicell_window_param():
    # win_cells threads through; the two 12 mm fields are found at any sane
    # window (the smallest field may drop at a coarser window — expected, a
    # bigger window resolves small patches less well).
    assert len(_cands(_fixture()[0], win_cells=3.0)) >= 2


def test_segment_pieces_receiver_reverted():
    # the receiver's segment_pieces must NOT carry the exploratory options —
    # they live only on find_lattice_candidates (clean separation, no cruft).
    params = inspect.signature(segment.segment_pieces).parameters
    for gone in ("foreground", "angle_correct", "std_delta"):
        assert gone not in params
    assert not hasattr(segment, "STD_DELTA")


def test_annotate_smoke():
    import analyze_e019
    canvas, _ = _fixture()
    img = analyze_e019.annotate(canvas.astype(np.float32), _cands(canvas),
                                target_w=600)
    assert img.width == 600 and img.height > 0
