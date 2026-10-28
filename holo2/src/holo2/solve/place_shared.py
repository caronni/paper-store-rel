"""What every placement route shares: attachment, the frame, emission.

Five things live here, and each is here because it has (or will have)
more than one caller in family ``place``:

* **the attachment/footing gates** — ``pixel_work_is_attachable`` and
  ``reading_set_places``. The first is the M12 discipline, carried
  verbatim from the H3bis provider this wave deleted, and every route
  asks it before it reads a pixel. The second REPLACED
  ``working_footing_id`` at H4-LANES stage 1: which rungs a run reads is
  declared policy now (``engine.recipe.RecipeEntry.reading_set``, data
  that rides ``SessionIdentity``), not a hard max-over-ppc computed at
  the door. Its stage-1 default reproduces that max exactly, window for
  window.
* **the frame bridge, both ways** — :func:`page_affine_terms`, which
  turns an accepted placement (a v1 ``AffinePose`` over WINDOW cells,
  plus the rot90 and the page origin the address decode pinned) into the
  six-term page-cell affine holo2's records, done projection and tile map
  speak; and :func:`predict_from_page_affine`, its inverse, which is what
  a window holding an anchor's page affine and its OWN fitted pose needs
  to say where it sits (W2's consult, v1's ``_predict_from_hint``).
  One conversion, stated once, with the half-cell convention change
  written down instead of rediscovered. Since H4-LANES stage 2 the bridge
  also crosses the RUNG boundary — :func:`compose_to_native` and
  :func:`compose_from_native` below, and the section after this list.
* **the window preamble** — :func:`sample_window`: prepare the region,
  fit the pose, propose R5's seed, read the cells, core the mask. Every
  addressing route does exactly this before it has anything to address,
  and the two that exist do it identically.
* **the address→placement block** — :func:`place_addressed`: E022's
  bounded refinement, the straddle audit, and the page frame the emission
  wants. What differs between routes is how they REACHED an address; what
  happens to an address is one arithmetic.
* **THE SHARED EMISSION BLOCK** — the inline marginal-PAVA calibration
  and the per-tile evidence the H3bis worker carried at
  ``placement_h3bis.py:530-655``. Every accepting route runs it, and it
  is factored ONCE here for the reason H4-PLAN W1 gives: duplicating it
  per route would breach the file cap and would mint seven places for
  one semantic to drift. It stays a placement-side block until H5 lifts
  calibration into a provider of its own (census CA1); nothing about the
  records it writes changes when that happens — the ``pava-v1``
  calibration id, the per-tile :class:`EvidenceObservation` with its two
  staged blobs, and the ``carry_tile`` merge are exactly what the payload
  family already consumes.

A POSE IS FITTED ON A RUNG AND COMMITTED IN NATIVE PIXELS
---------------------------------------------------------
Ruling 2 (user, 2026-08-17), and v1's own law: "a pose is fitted on the
rung's own pixels at the rung's pitch and committed in the native frame".
v1 transported ALL pose geometry through native pixel space, and holo2's
``PoseRecord.native_affine`` is already named for that frame — the done
projection, the tile map, the regional fit and every consult read it
against the capture's NATIVE cell lattice. So exactly two places convert,
and both are exact rational arithmetic with one float rounding at the end:

* :func:`page_affine_terms` composes the rung->native scale INTO the
  fitted affine at commit, so what lands in the record is native-frame
  whichever lane fitted it;
* :func:`predict_from_page_affine` runs that backwards before it solves,
  because the window it is predicting FOR has fitted its own pose in its
  own rung's pixels.

Everything between them — the fit, the sampler, the refinement, the
audit — stays in the rung's own pixels and never learns there is another
frame; :func:`sample_window` is where the rung's pitch enters the window
layout and where its frame is picked up for the trip back out.
Everything after them — distances in capture cells, donors, done
projection — was already footing-blind (``geometry`` convention 2: one
capture-cell lattice, shared by every rung).

THE PUSH IS GONE; ITS GEOMETRY STAYED (H4 W2, the pull model)
--------------------------------------------------------------
Package 2 made an acceptance WRITE a hint state at every window around
it. The 2026-08-16 redesign deleted the write and kept the question:
hints are scheduling annotations, not facts, so a window consults the
COMMITTED POSES around it at fire time (``place_job``) and an acceptance
merely sets a flag on its neighbours, in memory, AFTER its pose commits
(``place_sched``). ``emit_placement`` therefore pushes nothing, and a
placement fire writes no hint state at all.

The ring and donor geometry below is still the whole answer to "who can
steer whom" — it just answers in two voices now.
:func:`ring_targets` + :func:`donor_targets` name who a placed window
PINGS; :func:`ring_targets` + :func:`donor_sources` name who a consulting
window may inherit a page frame FROM. There is no ring across regions and
none across captures: a page affine is the correspondence between one
printed page and one capture-region, shared by every footing of that
capture (``geometry`` convention 2) and meaningless anywhere else — which
is also why nothing here CONVERTS an affine.

The push's own machinery — the hint writes and the pusher's read-set —
was DELETED with the ``HintState`` family in the clean-slate sweep
(2026-08-16). Nothing computes a write for a neighbour any more: the two
questions it existed to answer are asked by the consult and the ping,
from the two functions above.

What DID change with the route (and what did not)
-------------------------------------------------
The H3bis block sampled each addressed tile through a page-wide affine
with its own aperture reader; the real route samples the window ONCE, at
its own fitted pose (``pose_fit.sample_segment`` — one order-1 read per
cell centre, E022's rule), and this block scatters those reads into
tiles. So the SCORES arrive from the pose kernel instead of from a second
sampler, and everything downstream of them is unchanged: the same
``detect.fit_calibration`` on the same spatial-parity split of the same
label population, the same ``CalibrationRecord``, the same LLR bound, the
same keys.

The label population is the reference field's — ``pose_audit`` already
computes it for the audit (:func:`~holo2.solve.pose_audit
.fragment_reference_sites` gives local points, expected bits and absolute
page coordinates), and it is the same printed-value set the H3bis block
built by hand from word and filler cells. The parity split is the same
one too: H3bis split on ``(y + x) % 2`` and E022's site parity is
``(131*y + 17*x) & 1``, which are the SAME mask because 131 and 17 are
both odd.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import numpy as np
from scipy import ndimage

from ..capture import FootingFrame
from ..core import (CaptureSha, FootingId, ProgressSink, ProtocolViolation,
                    ResourceKey, StagedBlob, Write, stage_array)
from ..format import FormatRowSpec, TILE_CELLS
from . import detect, pose_audit, pose_fit
from .geometry import (WINDOW_CELLS, WINDOW_STEP_CELLS, affine_matrix,
                       contains_rect, window_starts)
from .lattice_seed import LatticeSeedRecord, lattice_seed_key, supersedes
from .place_model import (E022_SUPPORT_FLOOR_SITES, AffinePose, AttemptBudget,
                          CellYX, PlacementConfig, PoseWindow)
from .placement import REFUSAL_POSE, REFUSAL_SUPPORT
from .plans import RegionView, WindowPlan
from .pose_audit import fragment_reference_sites
from .pose_fit import (AddressPatch, PreparedRegion, SegmentSample,
                       WindowFit)
from .quarantine import OUTCOME_CONTRADICTION, word_verdict
from .records import (CalibrationRecord, EvidenceObservation, HeldoutGate,
                      PoseRecord, calibration_key, carry_tile, evidence_key,
                      pack_piece_observation, ring_masks, tile_key)
from .reference import ReferenceFieldProvider, rotation_affine
from .view import PlaneView

#: The fit every accepting route commits, named in each calibration id.
CALIBRATION_ALGORITHM = "pava-v1"
#: Evidence is stored float32; the fit and the bound are float64.
LLR_STORE_DTYPE = np.float32


# ----------------------------------------------------------- the gates

def pixel_work_is_attachable(view: PlaneView, plan: WindowPlan, *,
                             config: PlacementConfig) -> bool:
    """Can a placement worker for ``plan`` dereference what it will read?

    Three things, one question, because one answer wakes them all: the
    surveyed region it poses in, the footing lane it reads through, and
    the pixels themselves. Since B9 the first two come back BY RECORD for
    every capture the store knows, so the pixels are what can say no.

    THE PIXELS HAVE TWO SOURCES (2026-08-17). An attached raster is one;
    the other is this state's own ``<state-dir>.prepared`` sibling, whose
    planes ARE the pixels every placement fire reads (W1a — no fire
    touches a raster) and whose names became pronounceable without a file
    when the backing scalar joined the capture record. A crash-cut resume
    whose derived pixels survived therefore re-earns its placement tail
    with no scan declared at all. The raster is asked FIRST and
    short-circuits, so a session that has the file behaves exactly as
    before and never builds a plane at admission time.

    BOTH SOURCES ARE ASKED PER RUNG since H4-LANES stage 1, which is a
    generalisation and not a change: the first question is the plan's
    FOOTING's pixels (``has_footing_pixels`` — the attached scan at the
    native rung, its derived file or a raster to derive it from below
    that), and the second is that footing's own prepared planes. At the
    native rung both read exactly what they read before, because the
    native rung IS the attached scan and its prepared planes are the ones
    that already stand.

    THE WAKE STORY IS UNCHANGED, and that is a statement about direction,
    not luck: a prepared plane only ever appears through a session that
    HAD the raster, so within one run the second source cannot arrive
    after this question was answered no. The single honest wake stays
    ``attachment_key`` — attaching the file supplies whichever of the
    three is missing, and it is also what would produce the planes and
    the rungs.
    """
    if not (view.has_region(plan.region_id)
            and view.has_footing(plan.footing_id)):
        return False
    if view.has_footing_pixels(plan.footing_id):
        return True
    return view.prepared_region(view.region(plan.region_id), config=config,
                                footing_id=plan.footing_id) is not None


#: The reading-set vocabulary, in the plane's spelling of
#: ``engine.recipe``'s (which this package may not import): the same
#: wall-crossing discipline the footing selector and the tier table use,
#: pinned equal in ``tests/engine/test_cost_vocabulary.py``.
READING_FINEST = "finest"
READING_ALL = "all"
READING_SETS = frozenset({READING_FINEST, READING_ALL})


def reading_set_places(view: PlaneView, plan: WindowPlan,
                       reading_set: str) -> bool:
    """Does the declared reading set place THIS window's footing?

    ``working_footing_id``'s replacement (H4-LANES stage 1), and the
    difference is where the answer comes from rather than what it is.
    The old function computed a hard max over ppc and called it "the
    working footing"; its argument was sound — the measured target is
    ~8 px/dot (CLAUDE.md channel facts, e016.2 / e012.3), the ladder
    never upsamples, so "as close to 8 px/dot as the capture allows"
    always resolves to the finest rung — but it was an argument the code
    made silently, once, for every lineage, with no way for a run to
    declare otherwise and no way for a state to record which reading it
    was built under. The reading is DATA now and rides the recipe's
    entries into ``SessionIdentity``.

    ``finest`` reproduces the old answer window for window: the finest
    rung of the plan's own capture, compared by ppc exactly as before.
    ``all`` is the cascade, where every rung places and the coarse lanes
    are extra decoding trajectories rather than cheap first passes.

    An UNKNOWN reading set places nothing, deliberately: a policy nobody
    implements must not silently degrade into the widest one, and the
    recipe validates the vocabulary at construction, so reaching this
    branch means a caller composed a scheduler by hand.
    """
    if reading_set == READING_ALL:
        return True
    if reading_set != READING_FINEST:
        return False
    finest: tuple[object, FootingId] | None = None
    for footing_id in view.footing_ids("all"):
        footing = view.footing(footing_id)
        if footing.capture_sha256 != plan.capture_sha256:
            continue
        candidate = (footing.ppc, footing_id)
        if finest is None or candidate > finest:
            finest = candidate
    return finest is not None and plan.footing_id == finest[1]


# ------------------------------------------------------- the frame bridge

def _rescale_pixels(terms: tuple[float, ...],
                    scale: Fraction) -> tuple[float, ...]:
    """One page affine's PIXEL side, rescaled by an exact rational.

    A rung pixel ``j`` is the area average of native pixels
    ``[j*s, (j+1)*s)`` (``capture.scale_space``), so its centre sits at
    native index ``s*(j + 1/2) - 1/2`` — which is the map applied here,
    ``out = s*(in + 1/2) - 1/2``, on both the linear terms and the
    offset. It is a similarity on the pixel axis alone: the page-cell
    side of the affine is untouched, because a printed cell measures the
    same paper at every rung.

    RATIONAL IN, RATIONAL THROUGH, ONE FLOAT OUT. ``Fraction(float)`` is
    exact (a float IS a binary rational), the scale is exact, the
    products and the ``(s-1)/2`` shift are exact, and each term is
    rounded exactly once on the way out. So the composition is not
    "accurate enough" — it is the correctly rounded value of an
    arithmetic that never left the rationals, and at ``s == 1`` it is the
    identity by construction rather than by luck.
    """
    if len(terms) != 6:
        raise ValueError("an affine has 6 terms")
    shift = (scale - 1) / 2
    a, b, c, d, e, f = (Fraction(float(term)) for term in terms)
    return (float(a * scale), float(b * scale), float(c * scale + shift),
            float(d * scale), float(e * scale), float(f * scale + shift))


def compose_to_native(terms: tuple[float, ...],
                      frame: FootingFrame) -> tuple[float, ...]:
    """A page affine fitted in ONE RUNG's pixels, restated in native ones.

    Ruling 2's commit half (module docstring). ``frame`` is the rung the
    pose was fitted on (``plane.footing_frame``), and its transform
    carries the exact rational ``native / rung`` scale; the native frame
    is the identity member of that type, so a native-rung pose returns
    its own terms unchanged and no lane that stands today can be renamed
    by this.
    """
    if frame.is_native:
        return tuple(float(term) for term in terms)
    return _rescale_pixels(terms, frame.transform.source_per_output)


def compose_from_native(terms: tuple[float, ...],
                        frame: FootingFrame) -> tuple[float, ...]:
    """:func:`compose_to_native` backwards — a native affine, in a rung.

    What a CONSULT needs: every committed pose is native-frame, and the
    window being predicted for has fitted its own pose in its own rung's
    pixels, so the anchor's frame has to come down to that rung before
    the two can be composed at all.
    """
    if frame.is_native:
        return tuple(float(term) for term in terms)
    return _rescale_pixels(terms, 1 / frame.transform.source_per_output)


def page_affine_terms(pose: AffinePose, patch_shape_yx: tuple[int, int],
                      rot_k: int, page_origin_yx: tuple[int, int],
                      frame: FootingFrame | None = None,
                      ) -> tuple[float, ...]:
    """The six-term page-cell -> native-pixel affine of one placement.

    The pose kernel works in WINDOW cells: ``pose`` maps a window-local
    cell index to native pixels, and an accepted address says where the
    window sits on the page — its ``rot90`` orientation ``rot_k`` and the
    page cell ``page_origin_yx`` that the ROTATED patch's ``[0, 0]``
    occupies. Composing the two inverts the rotation:

        page  = R @ local + t + origin           (``rotation_affine``)
        local = R.T @ (page - t - origin)        (R is orthogonal)
        native = M @ local + O
               = (M R.T) page - (M R.T)(t + origin) + O

    ONE convention change rides along, and it is the difference that
    would silently cost half a cell: v1's affine maps cell CENTRES (its
    phase objective lands integer indices on them), holo2's maps cell
    EDGES — cell ``(cy, cx)`` names the corner of ``[cy, cy+1) x
    [cx, cx+1)`` and every holo2 sampler adds the sub-cell offset itself.
    So the translation carries an extra ``-A @ (0.5, 0.5)``.

    ``frame`` is the RUNG ``pose`` was fitted on (H4-LANES stage 2,
    ruling 2). The kernel works in that rung's pixels, so the last act
    before a pose becomes a record is composing the exact rational
    rung->native scale into it (:func:`compose_to_native`). Omitting it
    means the native rung, which is what every caller meant before there
    were lanes; at the native rung the composition is the identity, so
    every term this function has ever returned it returns still.
    """
    matrix = pose.matrix()
    rotation, translation = rotation_affine(rot_k, patch_shape_yx)
    linear = matrix @ rotation.T
    shift = translation + np.asarray(page_origin_yx, np.float64)
    offset = (np.asarray(pose.origin_yx, np.float64) - linear @ shift
              - linear @ np.full(2, 0.5))
    terms = (float(linear[0, 0]), float(linear[0, 1]), float(offset[0]),
             float(linear[1, 0]), float(linear[1, 1]), float(offset[1]))
    return (terms if frame is None
            else compose_to_native(terms, frame))


def predict_from_page_affine(page_affine: tuple[float, ...],
                             target_pose: AffinePose,
                             target_shape_yx: tuple[int, int],
                             frame: FootingFrame | None = None,
                             ) -> tuple[int, CellYX]:
    """Where a window sits, given a page frame and the window's own fit.

    :func:`page_affine_terms` run backwards, and the ONE thing a consult
    needs: the anchor pose carries a page-cell -> native-pixel affine
    (its own), the consulting window has fitted its own local pose, and
    what the bounded local search must be centred on is the integer page
    cell the target's rotated ``[0, 0]`` would occupy under that frame.

    v1 computes this in ``place.py:245-267`` (``_predict_from_hint``) and
    the arithmetic here is that one, with two differences that are
    conventions rather than steps:

    * v1's hint carries its ``rot_k`` explicitly; holo2's pose does not
      (a pose's rotation is composed INTO its affine), so the orientation
      is recovered first — ``A = M R.T`` makes ``R`` the rot90 frame whose
      composition with this window's own Jacobian reproduces the page
      frame, and the four candidates are 90 degrees apart, so the argmin
      is exact rather than a fit. A WRONG answer here cannot place
      anything wrong: it lands the search 90 degrees out, every candidate
      misses its bars, and the route reports a refusal.
    * holo2's page affine maps cell EDGES where v1's maps cell CENTRES, so
      v1's offset is recovered by adding ``A @ (0.5, 0.5)`` back before
      the solve. ``int(round(...))`` on the resulting ``float64`` is v1's
      own idiom (numpy half-to-even), kept because the exact-half offsets
      a rot90 transport produces land on it.

    ``frame`` is the rung ``target_pose`` was fitted on (H4-LANES stage
    2). The anchor's affine is native-frame — every committed pose is —
    and this window's own pose is not, so the anchor comes DOWN to this
    rung before anything is composed (:func:`compose_from_native`). At
    the native rung that is the identity, so the arithmetic below is the
    one it has always been.
    """
    page_affine = (page_affine if frame is None
                   else compose_from_native(page_affine, frame))
    matrix = affine_matrix(page_affine)
    page_jacobian = matrix[:, :2]
    local_jacobian = target_pose.matrix()
    rotations = [rotation_affine(rot_k, target_shape_yx) for rot_k in range(4)]
    rot_k = min(range(4), key=lambda k: float(np.linalg.norm(
        local_jacobian @ rotations[k][0].T - page_jacobian)))
    # v1's cell-CENTRE offset, recovered from holo2's cell-EDGE one.
    page_offset = matrix[:, 2] + page_jacobian @ np.full(2, 0.5)
    page_at_local_zero = np.linalg.solve(
        page_jacobian,
        np.asarray(target_pose.origin_yx, np.float64) - page_offset)
    origin = page_at_local_zero - rotations[rot_k][1]
    return rot_k, (int(round(origin[0])), int(round(origin[1])))


# --------------------------------------------------- the window preamble

def address_core(mask: np.ndarray, erode_cells: int) -> np.ndarray:
    """E022's address core: the sampled mask, eroded, never empty."""
    if erode_cells <= 0:
        return np.asarray(mask, bool)
    eroded = np.asarray(ndimage.binary_erosion(mask, iterations=erode_cells))
    return eroded if eroded.any() else np.asarray(mask, bool)


@dataclass(frozen=True)
class WindowSample:
    """One window prepared, fitted and read — or the reason it was not.

    ``seed_writes`` rides even a REFUSAL, and that is R5's shape rather
    than politeness: a window whose spectral fit cleared the geometric
    gates measured fundamentals a smaller neighbour can use, whether or
    not its own phase objective closed.

    ``retire`` marks the two refusals that are statements about the
    WINDOW (its region carries no lattice, its pixels did not
    materialise) rather than about this attempt, so a route need not
    re-derive which of its refusals are terminal from a string.

    ``frame`` is the RUNG this sample was read on (H4-LANES stage 2):
    the fit, the patch and every pose derived from them live in its
    pixels, so the value travels with them to the one place that leaves
    that frame (:func:`compose_to_native`, at commit). ``None`` on a
    refusal, where there is no pose to commit.
    """

    refusal: str | None = None
    retire: bool = False
    seed_writes: tuple[Write, ...] = ()
    region: PreparedRegion | None = None
    patch: AddressPatch | None = None
    frame: FootingFrame | None = None


def pose_window(region: RegionView, plan: WindowPlan,
                pitch_px: float) -> PoseWindow:
    """A window plan's extent as the pose kernel names a window.

    The window LATTICE is holo2's (``plans.window_plans_for``, the OR-9
    geometry): its extent in capture cells is the durable name, and the
    kernel wants that extent in the prepared region's pixel frame.
    ``PoseWindow.window_id`` is v1's fit-local ordinal and has no holo2
    meaning — the durable name is ``plan.window_id`` — so it is 0 here,
    and ``support_estimate`` is the plan's exact supported cell count
    rather than v1's ``[::4, ::4]`` estimate.

    ``pitch_px`` is THE RUNG'S pitch (H4-LANES stage 2), which is what
    makes "the prepared region's pixel frame" above true on a coarse
    lane: the extent is in capture CELLS, shared by every rung, and the
    pixels under it are not. It is a parameter rather than a lookup
    because the caller has just prepared the plane and holds the exact
    number (``PreparedRegion.pitch_prior``, itself
    ``FootingFrame.pitch_px`` of the region's native pitch) — and because
    a default would be a native pitch quietly applied to coarse pixels.
    At the native rung it IS ``region.lattice.pitch_px`` as a float, so
    every window this ever laid out it lays out identically.
    """
    assert region.lattice is not None
    pitch = float(pitch_px)
    cy0, cx0, cy1, cx1 = plan.extent_cells
    return PoseWindow(
        0, 0, (int(round(cy0 * pitch)), int(round(cx0 * pitch))),
        (cy1 - cy0, cx1 - cx0), 0, plan.supported_cells)


def seed_writes(current: LatticeSeedRecord | None, plan: WindowPlan,
                fit: WindowFit) -> tuple[Write, ...]:
    """Propose this fit's own measurement, if it beats the standing one (R5)."""
    measured = fit.unconditioned_seed
    if measured is None:
        return ()
    proposed = LatticeSeedRecord(
        footing_id=plan.footing_id, region_id=plan.region_id,
        rows=measured.rows, source_window_id=plan.window_id,
        source_support_cells=plan.supported_cells)
    if proposed == current or not supersedes(proposed, current):
        return ()
    return (Write(lattice_seed_key(plan.footing_id, plan.region_id),
                  proposed),)


def sample_window(view: PlaneView, plan: WindowPlan, *,
                  config: PlacementConfig,
                  progress: ProgressSink) -> WindowSample:
    """Prepare, fit, seed, read and core one window — every route's opening.

    The pixels are the region's PREPARED plane, mapped once per region and
    handed to every fire (W1a) — never a raster, which is why an
    unattached capture whose prepared planes survived is a perfectly
    ordinary fire here. What is not optional is the PLANE: the provider
    gated pixel availability before minting this worker (M12), so having
    neither a raster nor a prepared plane means core's own protocol was
    broken — which is what ``ProtocolViolation`` names, and it is no
    longer a bare ``KeyError`` crossing the worker boundary. A refusal
    with the raster in hand is the geometric one and RETIRES the window,
    as it always did.

    EVERY PIXEL IT TOUCHES IS THE PLAN'S OWN RUNG'S (H4-LANES stage 2):
    the prepared plane is that lane's, and so is the pitch the window
    extent is laid out at, so a coarse window fits a coarse lattice on
    coarse pixels instead of a native lattice on the wrong ones. The
    rung's frame rides back out on the sample, because the pose the
    caller will commit is in these pixels and has to leave them.
    """
    region = view.region(plan.region_id)
    if not region.schedulable:
        return WindowSample("unschedulable_region", retire=True)
    prepared = view.prepared_region(region, config=config,
                                    footing_id=plan.footing_id)
    if prepared is None:
        if view.raster(plan.capture_sha256) is None:
            raise ProtocolViolation(
                f"armed for capture {plan.capture_sha256[:12]}, which has "
                "neither attached pixels nor a prepared plane on disk — the "
                "placement provider declines those (M12)")
        return WindowSample("region_not_materialized", retire=True)
    frame = view.footing_frame(plan.footing_id)
    # A prepared plane exists, so the plane holds this rung — the frame
    # is the same lookup that named the file.
    assert frame is not None
    record = view.record(lattice_seed_key(plan.footing_id, plan.region_id))
    seed = record if isinstance(record, LatticeSeedRecord) else None
    fit = pose_fit.fit_window_pose(
        prepared, pose_window(region, plan, prepared.pitch_prior),
        config=config,
        lattice_seed=None if seed is None else pose_fit.LatticeSeed(seed.rows))
    progress.emit(1, "pose-fit")
    writes = seed_writes(seed, plan, fit)
    if fit.segment is None:
        # NOT durable, on purpose (R5): a better seed can still make this
        # window fit, and the seed key is in every read-set, so the
        # arrival of one re-arms the descriptor.
        return WindowSample(REFUSAL_POSE, seed_writes=writes)
    sample = pose_fit.sample_segment(prepared, fit.segment)
    if sample is None or int(sample.mask.sum()) < E022_SUPPORT_FLOOR_SITES:
        return WindowSample(REFUSAL_SUPPORT, seed_writes=writes)
    patch = pose_fit.make_address_patch(
        sample, address_core(sample.mask, config.erode_cells))
    progress.emit(1, "window-sampled")
    return WindowSample(seed_writes=writes, region=prepared, patch=patch,
                        frame=frame)


def place_addressed(region: PreparedRegion, patch: AddressPatch, *,
                    page: int, page_origin_yx: CellYX, rot_k: int,
                    reference: ReferenceFieldProvider, config: PlacementConfig,
                    budget: AttemptBudget, progress: ProgressSink,
                    frame: FootingFrame | None = None,
                    ) -> AcceptedPlacement | None:
    """Refine, audit, and hand the emission block a page frame.

    Route-agnostic since W2: what a route decides is WHICH address its
    window is tested against; what happens to an accepted address — E022's
    bounded refinement, the re-read, the binomial-impurity straddle audit
    — is one arithmetic with one caller's worth of decisions in it.

    ``frame`` is the rung all of that happened on, relayed to
    :func:`page_affine_terms` so the affine this hands back is
    native-frame (ruling 2). Nothing between here and there converts:
    the refinement, the resample and the audit all read the same
    prepared plane the fit did.
    """
    refined = pose_audit.refine_patch_pose(
        region, patch, reference, page, page_origin_yx, rot_k, config,
        resample=pose_fit.sample_segment)
    if (refined is not None and int(refined.sample.mask.sum())
            >= E022_SUPPORT_FLOOR_SITES):
        patch = pose_fit.refresh_address_patch(
            patch, refined.sample,
            address_core(refined.sample.mask, config.erode_cells))
    progress.emit(1, "refine")
    audited, refused, _kept, _residual = pose_audit.audit_segment(
        patch.sample, patch.mask, reference, page, page_origin_yx, rot_k,
        config, min_support=budget.min_support)
    progress.emit(1, "audit")
    if refused:
        return None
    return AcceptedPlacement(
        page=page, rot_k=rot_k, page_origin_yx=page_origin_yx,
        # Negated luma: larger means more ink, the polarity the monotone
        # PAVA map and the tile chain both require.
        scores=-np.asarray(patch.sample.means, np.float64),
        observed=np.asarray(audited, bool),
        affine=page_affine_terms(patch.frame_pose, patch.shape_yx, rot_k,
                                 page_origin_yx, frame),
        # The REFINED sample, carried so the emission can harvest the
        # pilot reads under the audited core WITH the pose that made
        # them (W5). It is the sample every other field above is
        # derived from, so carrying it adds no read and no copy.
        sample=patch.sample)


# ---------------------------------------------------------- the emission

@dataclass(frozen=True)
class AcceptedPlacement:
    """One accepted window, as the emission block reads it.

    ``scores`` and ``observed`` are WINDOW-LOCAL, in the sampler's own
    (unrotated) frame: ``scores`` is negated luma, so larger means more
    ink, which is the polarity ``detect``'s monotone PAVA map requires;
    ``observed`` is the AUDITED core — the cells the straddle audit left
    standing, which is exactly the set v1 harvests observations under.

    ``sample`` is the refined :class:`~holo2.solve.pose_fit.SegmentSample`
    the three arrays above came from, carried since W5 so the emission
    can harvest this placement's pilot reads (``pose_audit
    .observations_for_segment``) without re-sampling. ``None`` is a test
    double's placement, which harvests nothing and reduces nothing.
    """

    page: int
    rot_k: int
    page_origin_yx: tuple[int, int]
    scores: np.ndarray
    observed: np.ndarray
    affine: tuple[float, ...]
    sample: SegmentSample | None = None


@dataclass(frozen=True)
class Emission:
    """What the block proposes: an outcome, its writes, its staged bulk."""

    outcome: str
    writes: tuple[Write, ...] = ()
    blobs: tuple[StagedBlob, ...] = ()
    tiles: int = 0

    @property
    def accepted(self) -> bool:
        return self.outcome == "accepted"


# ----------------------------------------------- the ring/donor geometry

def ring_targets(view: PlaneView, plan: WindowPlan) -> tuple[WindowPlan, ...]:
    """The eight windows around this one, on ITS OWN footing and region.

    Computed on the REGION'S LATTICE, never on the set of plans that
    happen to exist: a neighbour is the window one step away in
    ``geometry.window_starts``' own enumeration, and a start that carries
    no plan (the region supports no cell of it) simply has nobody there.
    Deriving the ring from the surviving plans instead would
    quietly promote a two-steps-away window to "immediate" wherever a
    window was dropped.

    THE RING IS ASYMMETRIC AT AN EDGE, and that is the flush shift, not a
    defect: the last start of an axis is pulled IN so its window ends
    flush against the far edge (``window_starts``), so an edge window's
    inner neighbour is one full step away while it is itself less than a
    step from its predecessor. Membership is by lattice INDEX, so the
    ring is still exactly the adjacent windows; only the distances — and
    therefore the scores — are uneven, which is what the score is for.
    """
    region = view.region(plan.region_id)
    if not region.schedulable:
        return ()
    assert region.lattice is not None
    rows, cols = region.lattice.shape_cells
    starts_y = window_starts(rows)
    starts_x = window_starts(cols)
    index_y = {start: i for i, start in enumerate(starts_y)}
    index_x = {start: i for i, start in enumerate(starts_x)}
    # Plans come off this same enumeration (``plans.window_plans_for``),
    # so the lookups below cannot miss; a plan that somehow sat off its
    # region's lattice has no ring rather than an exception inside a
    # commit path.
    here_y = index_y.get(plan.extent_cells[0])
    here_x = index_x.get(plan.extent_cells[1])
    if here_y is None or here_x is None:
        return ()
    plans = {candidate.extent_cells: candidate
             for candidate in view.window_plans(plan.footing_id)
             if candidate.region_id == plan.region_id}
    ring: list[WindowPlan] = []
    for step_y in (-1, 0, 1):
        for step_x in (-1, 0, 1):
            if step_y == 0 and step_x == 0:
                continue
            iy, ix = here_y + step_y, here_x + step_x
            if not (0 <= iy < len(starts_y) and 0 <= ix < len(starts_x)):
                continue
            cy0, cx0 = starts_y[iy], starts_x[ix]
            neighbour = plans.get((cy0, cx0, min(rows, cy0 + WINDOW_CELLS),
                                   min(cols, cx0 + WINDOW_CELLS)))
            if neighbour is not None:
                ring.append(neighbour)
    return tuple(ring)


def donor_targets(view: PlaneView, plan: WindowPlan) -> tuple[WindowPlan, ...]:
    """The FINER-footing windows this window's extent covers (item 6).

    "Finer" is more pixels per cell (``FootingSpec.ppc``, the ordering
    ``reading_set_places`` reads), so this is the downhill direction: a
    pose committed on a coarse lane steers the fine lane that will have
    to read the same ink. There is no uphill push and no separate donor
    ROUTE — a consult reads every anchor it can see, and a donor is
    simply the one that scores 0.

    Covering is asked in CAPTURE CELLS, which every footing of a capture
    shares (``geometry`` convention 2), so no frame conversion happens
    here and a colocated donor is exactly colocated. With the lattices
    identical, "covers" resolves to the same extent today; it is written
    as containment because containment is the rule, and equality is the
    case that rule currently has.
    """
    source = view.footing(plan.footing_id)
    targets: list[WindowPlan] = []
    for footing_id in view.footing_ids("all"):
        footing = view.footing(footing_id)
        if (footing.capture_sha256 != plan.capture_sha256
                or footing.ppc <= source.ppc):
            continue
        targets.extend(
            candidate for candidate in view.window_plans(footing_id)
            if candidate.region_id == plan.region_id
            and contains_rect(plan.extent_cells, candidate.extent_cells))
    return tuple(targets)


def donor_sources(view: PlaneView, plan: WindowPlan) -> tuple[WindowPlan, ...]:
    """:func:`donor_targets` run backwards — who could steer THIS window.

    The pull model asks the question in the consulting window's voice
    (H4 W2): the donors of a window are the COARSER-footing windows whose
    extent covers it, which is the same containment relation
    :func:`donor_targets` states, with the roles swapped. It is a separate
    function rather than a flag because the two are separate sentences —
    a push names who inherits, a consult names who can be inherited from —
    and the containment argument is directional.

    The ring needs no inverse: adjacency in ``window_starts``' own
    enumeration is symmetric, so :func:`ring_targets` already answers
    "which windows are one lattice step from me" in both voices.
    """
    target = view.footing(plan.footing_id)
    sources: list[WindowPlan] = []
    for footing_id in view.footing_ids("all"):
        footing = view.footing(footing_id)
        if (footing.capture_sha256 != plan.capture_sha256
                or footing.ppc >= target.ppc):
            continue
        sources.extend(
            candidate for candidate in view.window_plans(footing_id)
            if candidate.region_id == plan.region_id
            and contains_rect(candidate.extent_cells, plan.extent_cells))
    return tuple(sources)


def _calibration_writes(view: PlaneView, scope: ResourceKey,
                        fit: detect.CalibrationFit, search_bits: np.ndarray,
                        heldout_bits: np.ndarray,
                        ) -> tuple[tuple[Write, ...], tuple[StagedBlob, ...],
                                   ResourceKey]:
    """The fit, and the key the evidence will cite it by.

    The parameters are staged FIRST because they are part of the
    identity: a calibration is its scope, its algorithm and the numbers
    it fitted, and the numbers are bulk, so the id names them by the
    content address the sidecar gives them.

    The held-out delta is measured against the constant-rate model —
    ``detect`` states that HELDOUT never gates the marginal PAVA fit (its
    role is ownership/honesty), but ``HeldoutGate`` wants a delta and the
    only baseline a single window has is "predict the search ink rate for
    every cell". ``adopted`` follows ``detect``'s own acceptance.
    """
    assert fit.calibration is not None
    params = np.stack([fit.calibration.knots,
                       fit.calibration.probabilities]).astype(np.float64)
    blob = stage_array(params)
    key = calibration_key(scope, CALIBRATION_ALGORITHM, blob.ref.sha256)
    if view.record(key) is not None:
        return (), (), key
    rate = float(np.mean(search_bits)) if search_bits.size else 0.5
    rate = min(max(rate, 1e-6), 1.0 - 1e-6)
    held = np.asarray(heldout_bits, bool)
    baseline = float(-np.mean(
        np.where(held, np.log(rate), np.log1p(-rate)))) if held.size else 0.0
    delta = float(fit.heldout_logloss or 0.0) - baseline
    return (Write(key, CalibrationRecord(
        scope=scope, algorithm=CALIBRATION_ALGORITHM, params_ref=blob.ref,
        heldout=HeldoutGate(adopted=True, logloss_delta=delta))),
            ), (blob,), key


def _tile_writes(view: PlaneView, row: FormatRowSpec, pose: PoseRecord,
                 ty: int, tx: int, scores: np.ndarray, observed: np.ndarray,
                 calibration: detect.Calibration, calibration_id: ResourceKey,
                 halo: tuple[np.ndarray, np.ndarray],
                 ) -> tuple[tuple[Write, ...], tuple[StagedBlob, ...]]:
    """One tile's observation piece plus the tile-map merge that carries it."""
    llr = np.zeros((TILE_CELLS, TILE_CELLS), np.float64)
    llr[observed] = calibration.llr(scores[observed])
    stream = row.stream_ids[0]
    footing_id = pose.footing_id
    key = evidence_key(footing_id, pose.page, ty, tx, stream,
                       pose.resource_key())
    writes: list[Write] = []
    blobs: list[StagedBlob] = []
    if view.record(key) is None:
        blob = stage_array(llr.astype(LLR_STORE_DTYPE))
        # R3: the cells this pose actually SAW, durable beside the LLRs —
        # writing the mask down is what stops "observed, LLR 0" and "not
        # observed" being the same bytes on disk (§5.4) — and, since F1
        # (ruling J2-2), the one-cell CONTEXT HALO behind it, so a decode
        # can bin this tile's border ring the way v1's window-scoped ctx
        # apply bins it. The tile mask is still the blob's leading 4,096
        # bits, so every existing reader is unchanged
        # (``records.pack_piece_observation``).
        seen = stage_array(pack_piece_observation(observed, *halo))
        blobs.extend((blob, seen))
        writes.append(Write(key, EvidenceObservation(
            footing_id=footing_id, page=pose.page, ty=ty, tx=tx,
            stream=stream, pose_id=pose.resource_key(), llr_ref=blob.ref,
            observed_ref=seen.ref, calibration_id=calibration_id)))
    target = tile_key(pose.page, ty, tx, stream)
    merged = carry_tile(view.record(target), (footing_id,))
    if view.record(target) != merged:
        writes.append(Write(target, merged))
    return tuple(writes), tuple(blobs)


def emit_placement(view: PlaneView, *, row: FormatRowSpec,
                   plan: WindowPlan, pose: PoseRecord,
                   placement: AcceptedPlacement,
                   provider: ReferenceFieldProvider,
                   progress: ProgressSink) -> Emission:
    """Calibrate this window and write a piece per tile it observed.

    The order is the one the records need: the calibration is staged and
    keyed first (evidence cites it by name), then the pose, then a piece
    per tile whose cells this placement actually read. A tile the pose
    only clips still gets a piece — the observed mask says which cells,
    and the payload side's ownership freeze is what merges partial
    pieces from several windows into one view of a tile.

    Nothing is pushed from here since the pull model landed: what an
    acceptance offers its neighbours is a flag the SCHEDULER sets once
    this batch has committed, so the whole batch is facts and the whole
    of scheduling is in memory (``place_sched.PlacementScheduler.settle``).
    """
    window_id = plan.window_id
    tiles_yx = row.tiles_yx
    # PAGE orientation: the placement's own frame is the sampler's, and
    # ``rot_k`` is how it lies on the sheet (``np.rot90``'s own sense —
    # the one ``ScoreMemo`` and the audit already scored it under).
    scores = np.rot90(placement.scores, placement.rot_k)
    observed = np.rot90(placement.observed, placement.rot_k)
    origin_y, origin_x = placement.page_origin_yx
    points, expected, absolute = fragment_reference_sites(
        placement.observed, provider, placement.page,
        placement.page_origin_yx, placement.rot_k)
    if not expected.size:
        return Emission("no_labels")
    label_scores = placement.scores[points[:, 0], points[:, 1]]
    ids = (absolute[:, 0].astype(np.int64) * row.cells_yx[1]
           + absolute[:, 1].astype(np.int64))
    # The SEARCH/HELDOUT split is the spatial parity of the absolute page
    # cell: disjoint by construction (what ``detect`` requires) and
    # balanced over the window, which a contiguous split is not.
    parity = ((absolute[:, 0] + absolute[:, 1]) % 2 == 0)
    name = str(window_id)
    bits = np.asarray(expected, np.uint8)
    fit = detect.fit_calibration(
        detect.CalibrationObservations(name, label_scores[parity],
                                       bits[parity], ids[parity]),
        detect.CalibrationObservations(name, label_scores[~parity],
                                       bits[~parity], ids[~parity]))
    if not fit.accepted or fit.calibration is None:
        # This refusal drops the WHOLE emission, the already-accepted pose
        # included: ``pose`` has no write of its own before the calibration
        # gate (below), so a calibration-poor window commits no pose either
        # — carried behaviour of the inline calibration block, not stated
        # anywhere until now. The pose coverage and any future refinement
        # would otherwise have used is simply lost on edge windows whose
        # label population calibrates badly (H5/CA1 ledger entry,
        # `solve/DESIGN.md`).
        return Emission(f"calibration_{fit.reason}")
    # W5's third layer, asked BEFORE a byte of this placement's evidence
    # is proposed: the known-position reduce over this fire's own pilot
    # reads, at this fire's own (capture, footing) scope (ruling 4). A
    # contradiction returns instead of emitting — the placement writes
    # NO evidence at all, and what it does write is the durable fact
    # plus the condemnation of the standing side.
    verdict = word_verdict(
        view, pose=pose, provider=provider, stream=row.stream_ids[0],
        capture_id=str(plan.capture_sha256), sample=placement.sample,
        observed=placement.observed, page=placement.page,
        page_origin_yx=placement.page_origin_yx, rot_k=placement.rot_k)
    if verdict:
        return Emission(OUTCOME_CONTRADICTION, verdict.writes)
    cal_writes, cal_blobs, calibration_id = _calibration_writes(
        view, window_id, fit, bits[parity], bits[~parity])
    writes: list[Write] = list(cal_writes)
    blobs: list[StagedBlob] = list(cal_blobs)
    writes.append(Write(pose.resource_key(), pose))
    height, width = observed.shape
    # The window's PROVISIONAL INK, once, for the halo each piece carries
    # (F1, ruling J2-2): ``marginal > 0`` on this window's own calibrated
    # scale, which is the same array a piece's stored LLRs are cut from —
    # so a tile's halo and its interior agree by construction.
    ink = np.zeros(observed.shape, bool)
    ink[observed] = fit.calibration.llr(scores[observed]) > 0.0
    tiles = 0
    for ty in _tile_span(origin_y, height, tiles_yx[0]):
        for tx in _tile_span(origin_x, width, tiles_yx[1]):
            piece = _tile_slice(scores, observed, (origin_y, origin_x),
                                ty, tx)
            if piece is None:
                continue
            tile_scores, tile_observed = piece
            tile_writes, tile_blobs = _tile_writes(
                view, row, pose, ty, tx, tile_scores, tile_observed,
                fit.calibration, calibration_id,
                ring_masks(observed, ink, (origin_y, origin_x), ty, tx))
            writes.extend(tile_writes)
            blobs.extend(tile_blobs)
            tiles += 1
            progress.emit(1, "tile-observed")
    if not tiles:
        return Emission("no_observed_tile")
    return Emission("accepted", tuple(writes), tuple(blobs), tiles)


def _tile_span(origin: int, extent: int, tiles: int) -> range:
    """Every tile index one axis of a placement can touch, clipped."""
    first = max(0, origin // TILE_CELLS)
    last = min(tiles, -(-(origin + extent) // TILE_CELLS))
    return range(first, max(first, last))


def _tile_slice(scores: np.ndarray, observed: np.ndarray,
                origin_yx: tuple[int, int], ty: int, tx: int,
                ) -> tuple[np.ndarray, np.ndarray] | None:
    """One tile's 64x64 window onto a page-oriented placement, or None."""
    origin_y, origin_x = origin_yx
    height, width = observed.shape
    y0 = max(origin_y, ty * TILE_CELLS)
    y1 = min(origin_y + height, (ty + 1) * TILE_CELLS)
    x0 = max(origin_x, tx * TILE_CELLS)
    x1 = min(origin_x + width, (tx + 1) * TILE_CELLS)
    if y1 <= y0 or x1 <= x0:
        return None
    seen = observed[y0 - origin_y:y1 - origin_y, x0 - origin_x:x1 - origin_x]
    if not seen.any():
        return None
    tile_observed = np.zeros((TILE_CELLS, TILE_CELLS), bool)
    tile_scores = np.zeros((TILE_CELLS, TILE_CELLS), np.float64)
    rows = slice(y0 - ty * TILE_CELLS, y1 - ty * TILE_CELLS)
    cols = slice(x0 - tx * TILE_CELLS, x1 - tx * TILE_CELLS)
    tile_observed[rows, cols] = seen
    tile_scores[rows, cols] = scores[
        y0 - origin_y:y1 - origin_y, x0 - origin_x:x1 - origin_x]
    return tile_scores, tile_observed


__all__ = [
    "AcceptedPlacement", "CALIBRATION_ALGORITHM", "Emission",
    "LLR_STORE_DTYPE", "READING_ALL", "READING_FINEST", "READING_SETS",
    "WindowSample", "address_core", "compose_from_native",
    "compose_to_native", "donor_sources",
    "donor_targets", "emit_placement", "page_affine_terms",
    "place_addressed", "pixel_work_is_attachable", "pose_window",
    "predict_from_page_affine", "reading_set_places", "ring_targets",
    "sample_window", "seed_writes",
]
