"""RULING 2: a pose is fitted on a rung and committed in native pixels.

H4-LANES stage 2's geometry verdict, in three claims that fail for three
different reasons:

1. **THE PIN.** At the native rung the whole seam is the IDENTITY. The
   frame the kernel now carries contributes nothing to the affine, the
   pitch the window extent is laid out at is the region's own, and the
   terms committed are bit-for-bit the terms the frameless expression
   produced before this wave. A single-lane run therefore cannot tell
   stage 2 happened — which is the bar the wave is allowed to land under.
2. **THE ARITHMETIC IS EXACT.** ``compose_to_native`` is checked against
   an INDEPENDENT ``Fraction`` transcription of its own rule, term by
   term: rational in, rational through, one float out. A composition that
   converted the scale to a float first would drift here and nowhere
   else, because every other test in this file compares geometry with a
   tolerance.
3. **A COARSE-RUNG FIT LANDS WHERE THE NATIVE ONE DOES.** The two are
   fitted on different pixels, so they are not bit-equal and are not
   asserted to be; what is asserted is that once composed they describe
   the SAME printed lattice — the linear parts agree, and the corners
   agree to a fraction of a cell.

WHY THE OFFSET IS COMPARED MODULO ONE CELL, and why that is not a
weakening: the phase objective locks a lattice's sub-cell phase and
nothing more (``pose_fit._fit_phase`` sweeps ``[0.5, 1.5)``, exactly one
cell), so a bare fit determines the pose only up to an integer cell
shift. What pins the absolute page origin is the ADDRESS decode, which
runs after it and is not part of this seam. Comparing two bare fits
without that reduction would be comparing which integer cell each one
happened to lock, which is a property of the pixels and not of the frame
composition.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from holo2.capture import FootingFrame
from holo2.capture.ingest import ingest_capture
from holo2.core.commit import CommitEngine
from holo2.core.store import Store
from holo2.solve import pose_fit
from holo2.solve.place_model import AffinePose, PlacementConfig
from holo2.solve.place_shared import (compose_from_native, compose_to_native,
                                      page_affine_terms, pose_window)
from holo2.solve.plane import open_plane
from holo2.format.registry_rows import format_row
from conftest import make_session, registry

#: A print whose cell is EIGHT pixels wide, CAPTURED at 1600 dpi against
#: a c3 cell: ``native_pixels_per_cell(1600, 1/200 in) == 8``, so
#: ``auto_ppc_levels`` lays a 2/4/8 ladder and the 4-rung is a clean 2:1
#: decimation of pixels that are still four to a cell — comfortably above
#: the Nyquist edge the 2-rung sits on. The shared ``synthetic_print``
#: fixture is a 3-px cell at 600 dpi, whose only sub-native rung IS that
#: edge; this file needs a coarse lane that can actually fit.
CELL_PX = 8
#: The CAPTURE's declared dpi — a scan fact, not a printer's (P5; it was
#: called ``PRINT_DPI``, which is the thing holo2 no longer has).
CAPTURE_DPI = 1600.0
CODING = "c3-k-r0550"

#: The bound claim 3 makes, in CELLS, at the window's own corners after
#: the modulo-one-cell reduction. MEASURED on this fixture: 0.125 cells
#: between the 4-rung and the 8-rung (one native pixel of a
#: eight-pixel cell), so the bar has better than 2x headroom and a
#: composition that lost the half-pixel rung-centre term — which is worth
#: ``(s-1)/2 == 0.5`` native pixels, i.e. 0.0625 cells here — would still
#: pass. That term is what claim 2 exists to police; this one is about
#: the LATTICE landing in the right place.
CORNER_TOLERANCE_CELLS = 0.35


@pytest.fixture(scope="module")
def two_rung_print(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A synthetic print with an 8-pixel cell (module note: why 8).

    ``synthetic_print``'s construction at a coarser cell: a seeded binary
    cell field on paper white, which is fixture INPUT and never a receiver
    path or a channel claim.
    """
    rng = np.random.default_rng(20260817)
    field = np.kron(rng.random((128, 128)) < 0.5,
                    np.ones((CELL_PX, CELL_PX), bool))
    page = np.full((field.shape[0] + 300, field.shape[1] + 320), 235, np.uint8)
    page[100:100 + field.shape[0], 120:120 + field.shape[1]] = np.where(
        field, 30, 235)
    path = tmp_path_factory.mktemp("two-rung") / "print.png"
    Image.fromarray(page).save(path)
    return path


@pytest.fixture(scope="module")
def ladder(two_rung_print: Path,
           tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Ingest it, and hand back every rung's fitted first window.

    One ingest, several claims (the verdicts' own run-once law): the fit
    is the expensive part and every test below reads the same one.
    """
    row = format_row(CODING, (2, 2), 1)
    work = tmp_path_factory.mktemp("two-rung-state")
    store = Store.open_or_create(work / "state", make_session(), registry(),
                                 fsync=False)
    engine = CommitEngine(store)
    try:
        ingest_capture(engine, two_rung_print, CAPTURE_DPI, row.pitch_in,
                       directory=work / "derived")
        plane = open_plane(store, engine, row, ((two_rung_print, CAPTURE_DPI),))
        capture = plane.captures[0]
        region = capture.regions[0]
        assert region.lattice is not None, "the survey voted no pitch"
        config = PlacementConfig()
        rungs = {}
        for footing in capture.footings:
            prepared = plane.prepared_region(region, config=config,
                                             footing_id=footing.footing_id)
            frame = plane.footing_frame(footing.footing_id)
            plans = plane.window_plans(footing.footing_id)
            assert prepared is not None and frame is not None and plans
            plan = plans[0]
            fit = pose_fit.fit_window_pose(
                prepared, pose_window(region, plan, prepared.pitch_prior),
                config=config)
            rungs[footing.ppc] = dict(
                frame=frame, prepared=prepared, plan=plan, fit=fit,
                shape_yx=(plan.extent_cells[2] - plan.extent_cells[0],
                          plan.extent_cells[3] - plan.extent_cells[1]))
        yield dict(plane=plane, region=region, capture=capture, rungs=rungs,
                   native_ppc=capture.footings[-1].ppc)
    finally:
        store.close()


def _committed(rung: dict) -> tuple[float, ...]:
    """What this rung's fit would COMMIT: composed into native pixels."""
    assert rung["fit"].segment is not None
    return page_affine_terms(rung["fit"].segment.pose, rung["shape_yx"],
                             0, (0, 0), rung["frame"])


# ------------------------------------------------- (1) the native-rung pin

def test_the_ladder_really_has_a_coarse_rung_that_fits(ladder: dict) -> None:
    """The fixture's own guard: three rungs, and every one of them fitted.

    Asserted before anything is compared, because every claim below is
    vacuous on a ladder of one and every claim about a coarse fit is
    vacuous when the coarse fit refused.
    """
    rungs = ladder["rungs"]
    assert sorted(rungs) == [Fraction(2), Fraction(4), Fraction(8)]
    assert all(rung["fit"].segment is not None for rung in rungs.values()), (
        {str(ppc): rung["fit"].segment is not None
         for ppc, rung in rungs.items()})
    assert rungs[ladder["native_ppc"]]["frame"].is_native
    assert not rungs[Fraction(4)]["frame"].is_native


def test_the_native_rung_commits_exactly_what_the_frameless_call_did(
        ladder: dict) -> None:
    """THE PIN (ruling 2): byte-identical at the native rung.

    ``page_affine_terms``' fourth argument is the whole of what stage 2
    added to the commit path, and at the native rung it must contribute
    NOTHING — not "a negligible amount", nothing. Compared against the
    frameless call, which is the expression HEAD had.
    """
    native = ladder["rungs"][ladder["native_ppc"]]
    pose = native["fit"].segment.pose
    for rot_k in range(4):
        for origin in ((0, 0), (64, 128), (7, 3)):
            before = page_affine_terms(pose, native["shape_yx"], rot_k, origin)
            after = page_affine_terms(pose, native["shape_yx"], rot_k, origin,
                                      native["frame"])
            assert after == before, (rot_k, origin, before, after)


def test_the_native_rung_lays_the_window_out_at_the_regions_own_pitch(
        ladder: dict) -> None:
    """The other half of the pin: ``pose_window``'s new parameter.

    At the native rung the rung pitch IS ``region.lattice.pitch_px`` as a
    float (``FootingFrame.pitch_px`` returns it unchanged at the identity
    frame), so every window this ever laid out it lays out identically —
    asserted against the expression the function carried before, not
    against a re-call of itself.
    """
    region = ladder["region"]
    native = ladder["rungs"][ladder["native_ppc"]]
    plan, prepared = native["plan"], native["prepared"]
    assert prepared.pitch_prior == float(region.lattice.pitch_px)
    pitch = float(region.lattice.pitch_px)
    cy0, cx0, cy1, cx1 = plan.extent_cells
    window = pose_window(region, plan, prepared.pitch_prior)
    assert window.origin_yx_px == (int(round(cy0 * pitch)),
                                   int(round(cx0 * pitch)))
    assert window.shape_yx_cells == (cy1 - cy0, cx1 - cx0)
    # And a COARSE rung lays it out in ITS pixels, which is the change:
    # same cells, a pitch scaled by the rung's own exact rational.
    coarse = ladder["rungs"][Fraction(4)]
    assert coarse["prepared"].pitch_prior == pitch / 2.0
    assert pose_window(region, coarse["plan"],
                       coarse["prepared"].pitch_prior).origin_yx_px == (
        int(round(cy0 * pitch / 2.0)), int(round(cx0 * pitch / 2.0)))


# ------------------------------------------------ (2) the arithmetic is exact

@pytest.mark.parametrize("scale", ["2", "3/2", "5/3", "8/1", "12/5"])
def test_the_composition_is_the_exactly_rounded_rational(scale: str) -> None:
    """Term for term, against an INDEPENDENT ``Fraction`` transcription.

    The rule (``_rescale_pixels``): a rung pixel ``j`` is the area average
    of native ``[j*s, (j+1)*s)``, so its centre is at native index
    ``s*(j + 1/2) - 1/2`` — the pixel side of the affine scales by ``s``
    and its offset gains ``(s-1)/2``. Written here in exact rationals and
    rounded ONCE, which is what "rational in, rational through, one float
    out" has to mean if it is to be checkable: an implementation that did
    ``float(scale) * term`` would round twice and land elsewhere on at
    least one of these deliberately awkward terms.
    """
    factor = Fraction(scale)
    frame = FootingFrame(_TransformOf(factor), (4096, 4096))
    terms = (16.184, -0.0731, 1093.5000000000002,
             0.0359, 16.095000000000002, -7.25)
    shift = (factor - 1) / 2
    expected = []
    for index, term in enumerate(terms):
        exact = Fraction(term) * factor
        if index in (2, 5):
            exact += shift
        expected.append(float(exact))
    assert list(compose_to_native(terms, frame)) == expected


@pytest.mark.parametrize("scale", ["2", "3/2", "5/3", "8/1", "12/5"])
def test_the_two_directions_are_inverses_to_the_last_ulp(scale: str) -> None:
    """Down and back up: the round trip lands within one quantum.

    Not bit-equality — two roundings cannot promise that — but the claim
    that matters: the pair really are inverse maps, so a consult that
    brings an anchor DOWN to its rung and a commit that takes a pose UP
    from it are describing one geometry and not two.
    """
    frame = FootingFrame(_TransformOf(Fraction(scale)), (4096, 4096))
    terms = (16.184, -0.0731, 1093.5000000000002,
             0.0359, 16.095000000000002, -7.25)
    back = compose_from_native(compose_to_native(terms, frame), frame)
    for original, returned in zip(terms, back):
        assert abs(returned - original) <= 8 * np.spacing(abs(original) or 1.0)


def test_the_identity_frame_is_the_identity_in_both_directions() -> None:
    """No rounding at all at the native rung — the values ARE the values."""
    frame = FootingFrame.native((4096, 4096))
    terms = (16.184, -0.0731, 1093.5000000000002,
             0.0359, 16.095000000000002, -7.25)
    assert compose_to_native(terms, frame) == terms
    assert compose_from_native(terms, frame) == terms


class _TransformOf:
    """An ``AreaPixelTransform`` at an arbitrary scale, for the arithmetic.

    ``FootingFrame.of`` derives its transform from a ppc pair, which is a
    long way round for a test whose subject is one rational. This is the
    two attributes the composition reads and nothing else.
    """

    def __init__(self, scale: Fraction) -> None:
        self.source_per_output = scale
        self.is_identity = scale == 1


# ------------------------------------------- (3) the coarse rung's own fit

def test_a_coarse_rung_fit_commits_the_same_printed_lattice(
        ladder: dict) -> None:
    """Claim 3: different pixels, one lattice.

    The two fits read different arrays and cannot be bit-equal; what they
    must agree about is the printed geometry once composed. The LINEAR
    part is compared as a relative error (it is the cell-to-pixel
    Jacobian, and both rungs measured it independently), and the
    TRANSLATION at the window's four corners after reducing to
    ``(-1/2, 1/2]`` cells — the module docstring says why the reduction
    is the honest comparison and not a weakening.
    """
    native = ladder["rungs"][ladder["native_ppc"]]
    coarse = ladder["rungs"][Fraction(4)]
    fine_terms = np.asarray(_committed(native), np.float64)
    coarse_terms = np.asarray(_committed(coarse), np.float64)
    pitch = float(ladder["region"].lattice.pitch_px)

    fine_linear = fine_terms[[0, 1, 3, 4]]
    coarse_linear = coarse_terms[[0, 1, 3, 4]]
    assert np.allclose(coarse_linear, fine_linear, rtol=2e-3, atol=2e-3), (
        f"the two rungs measured different Jacobians: {coarse_linear} vs "
        f"{fine_linear}")

    cy0, cx0, cy1, cx1 = native["plan"].extent_cells
    worst = 0.0
    for cell_y in (cy0, cy1):
        for cell_x in (cx0, cx1):
            cell = np.array([cell_y, cell_x, 1.0], np.float64)
            fine = np.array([fine_terms[:3] @ cell, fine_terms[3:] @ cell])
            rough = np.array([coarse_terms[:3] @ cell,
                              coarse_terms[3:] @ cell])
            cells = (rough - fine) / pitch
            reduced = (cells + 0.5) % 1.0 - 0.5
            worst = max(worst, float(np.max(np.abs(reduced))))
    assert worst <= CORNER_TOLERANCE_CELLS, (
        f"the coarse rung's committed lattice sits {worst:.4f} cells from "
        f"the native rung's (bound {CORNER_TOLERANCE_CELLS})")


def test_a_coarse_pose_predicts_a_coarse_window_it_is_the_frame_of(
        ladder: dict) -> None:
    """The consult's half of the seam, end to end on real fits.

    A committed pose is native-frame; a window predicting from it has
    fitted its own pose in its own rung's pixels. So the prediction has
    to come DOWN through the same frame the commit went UP through, and
    the test of that is a pose composed from a rung and handed straight
    back to the same rung: the page origin it predicts must be the one it
    was composed at, which for a self-prediction is the origin itself.
    """
    from holo2.solve.place_shared import predict_from_page_affine

    for ppc in (Fraction(4), ladder["native_ppc"]):
        rung = ladder["rungs"][ppc]
        pose = rung["fit"].segment.pose
        for origin in ((0, 0), (64, 128)):
            terms = page_affine_terms(pose, rung["shape_yx"], 0, origin,
                                      rung["frame"])
            rot_k, predicted = predict_from_page_affine(
                terms, pose, rung["shape_yx"], rung["frame"])
            assert rot_k == 0
            assert predicted == origin, (str(ppc), origin, predicted)


def test_a_pose_composed_without_its_frame_would_land_a_rung_away(
        ladder: dict) -> None:
    """The negative control: the composition is doing real work.

    Claim 3 would pass a stopped clock if the coarse fit happened to
    produce native-looking numbers, so the same coarse fit is composed
    WITHOUT its frame (the pre-stage-2 expression) and must be wrong by
    about the rung's own scale — here 2x on the Jacobian.
    """
    coarse = ladder["rungs"][Fraction(4)]
    naive = np.asarray(page_affine_terms(
        coarse["fit"].segment.pose, coarse["shape_yx"], 0, (0, 0)),
        np.float64)
    composed = np.asarray(_committed(coarse), np.float64)
    ratio = composed[0] / naive[0]
    assert abs(ratio - 2.0) < 1e-9, (
        f"the frame composition scaled the Jacobian by {ratio}, not by the "
        "rung's own 2:1")


def test_the_pose_kernel_reads_the_rungs_own_pixels(ladder: dict) -> None:
    """What "fitted on the rung" means concretely, as shapes and pitches.

    Each rung's prepared plane is its OWN size and its own pitch, and the
    pose that comes out of it is in those pixels — which is why the
    commit has to compose at all.
    """
    rungs = ladder["rungs"]
    native = rungs[ladder["native_ppc"]]
    for ppc, rung in sorted(rungs.items()):
        scale = float(ladder["native_ppc"]) / float(ppc)
        assert rung["prepared"].pitch_prior == pytest.approx(
            native["prepared"].pitch_prior / scale)
        assert rung["prepared"].image.shape[0] <= (
            native["prepared"].image.shape[0] // scale + 1)
        origin = np.asarray(rung["fit"].segment.pose.origin_yx)
        assert (origin < np.asarray(rung["prepared"].image.shape) + 1).all()


def test_a_seed_belongs_to_its_rung_and_never_crosses(ladder: dict) -> None:
    """R5's key already says this; the numbers say why it must.

    A lattice seed is reciprocal FUNDAMENTALS — cycles per PIXEL — so a
    coarse rung's seed is off by the rung's scale on a fine one. The
    durable key is per (footing, region), so the two never meet; this
    pins the magnitude that makes the keying load-bearing rather than
    tidy.
    """
    rungs = ladder["rungs"]
    coarse = rungs[Fraction(4)]["fit"].lattice_seed
    fine = rungs[ladder["native_ppc"]]["fit"].lattice_seed
    assert coarse is not None and fine is not None
    coarse_y = abs(coarse.matrix()[0, 0])
    fine_y = abs(fine.matrix()[0, 0])
    assert coarse_y == pytest.approx(2.0 * fine_y, rel=0.05), (
        f"coarse fundamental {coarse_y}, fine {fine_y} — a seed that "
        "crossed rungs would refuse every gate it met")


def test_an_affine_pose_is_what_the_kernel_hands_back() -> None:
    """A guard on the type the two composers are about, not on a value."""
    pose = AffinePose((1.0, 2.0), ((3.0, 0.0), (0.0, 3.0)), (0.5, 0.5),
                      3.0, 0.0)
    assert pose.matrix().shape == (2, 2)
