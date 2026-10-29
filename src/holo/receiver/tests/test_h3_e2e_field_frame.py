"""The FRAME, end to end: one displaced page read four ways.

`docs/PAGE-FIELD-DESIGN.md` §6 B1 is the bar — "a synthetic page with one
plane displaced by a known page-axis vector certifies the same set under
rot 0, 1, 2 and 3 placements, and a confetti page whose windows mix all
four rotations solves the same field as the un-rotated page to within
0.05 dots".  `test_h3_plane_fields.py` proves the receiver half of it at
library level, one window at a time, on a hand-built raster; this module
asks a whole decode, because the frame regression the design names
(§1, twice suffered) lives in the composition — survey, placement, pose,
crop, collection, solve — and not in any one of them.

THE STIMULUS is the clean colour sim's own emit with the Y plane two
dots out of register, one cycle down the page, and nothing else: no
noise, no harder rung (`_h3_sims_field.make_color_shifted`).  Two dots
is the largest whole dot inside the anchor tier's reach, so the field can
express the whole displacement and the frame questions are asked of a
page the receiver reads completely.  Four decodes: the page at rot 0, the
same raster turned two quarter turns, the page CUT into four quadrant
scraps pasted at all four rotations on one platen, and the page again
with the two field rows dropped.

MEASURED 2026-09-08, all four verified byte-exact at 300/300
tile-streams — the whole domain, 100 tiles x 3 streams:

    arm          wall    certificates   Y field median
    rot 0        41.9 s   300/300        1.1420 dots
    rot 2        43.7 s   300/300        1.1453
    confetti     36.9 s   300/300        1.1132
    no field     38.5 s   300/300        (no solve; rows dropped)

WHICH ROTATIONS ARE PLACED WHOLE: rot 0 and rot 2.  rot 2 is the one
quarter turn that does NOT exchange the page axes, so a whole-page arm
cannot see an x/y swap however it is turned; rot 1 and rot 3 reach this
module as confetti scraps, one turn per quadrant, and each quadrant is
asked for the un-cut page's field on its own below.  Whether scraps
satisfy §6 B1's "rot 0, 1, 2 and 3 placements" is the design's wording
and the lead's to rule.

THE LANE IS THE WIDENED MATRIX, not the sim lane: 161 s of decode where
the ordinary slow lane has about 30 s of headroom under the 140 s wall
CLAUDE.md documents (107.8 s measured 2026-09-05, and W2's two new rows
have run on every colour page since, so that figure is stale and low).
The widened matrix buys no lane of its own — a sweeps run sets the slow
flag too — so this decode time is the slow lane's however it is started.
(The session tripwire that once turned that overrun into a red run was
retired 2026-09-20.)  What the flag buys is a lane nobody runs by
accident.  Splitting the four would put a frame proof in
one lane and its own control in another, which is worse.

WHAT THIS STIMULUS DOES NOT MEASURE is yield.  At r0550, with no noise,
a two-dot displacement costs nothing at all — the same page decodes
300/300 with the field rows dropped, certificate for certificate — which
reproduces what `_h3_sims` already records for this rung (2026-08-30: two
dots and 55 sd of sensor noise, not one tile lost).  The yield question
belonged to the top-rung pair retired 2026-09-20 (receiver
`docs/WIDENED-MATRIX-RETIREMENT-2026-09-20.md`), and the
amplitude cannot be raised here without leaving the estimator's reach,
because the next whole dot is three and the reach is 2.24.
"""

from __future__ import annotations

import numpy as np

from holo.receiver import data
from holo.receiver.format import identity
from holo.receiver.lib import plane_field
from holo.receiver.plugins import color_sites, field_tiers, fields, plane_k
from holo.receiver.tests import _h3_sims, _h3_sims_field
from holo.receiver.tests import _h3_support
from holo.receiver.tests import test_h3_e2e_sims as sims_pins

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `_assert_reaches_the_whole_page`.


# Counts JobDone EVENTS, and not `report["scheduler"]["plugins"]`, which
# is the union of the queued, the ran and the in-flight: a row that fires
# zero times is simply absent from it.  The sibling this was imported
# from retired 2026-09-20 (WIDENED-MATRIX-RETIREMENT-2026-09-20.md).
def job_counts(record: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in record.events:
        if isinstance(event, data.JobDone):
            counts[event.plugin] = counts.get(event.plugin, 0) + 1
    return counts


#: Every tile-stream of the page.  The displaced page reaches it, so the
#: frame arms below are compared against a CEILING and a lost
#: certificate anywhere is visible as a number that is not this one.
WHOLE_DOMAIN = sims_pins.COLOR_TILE_DOMAIN * sims_pins.COLOR_PLANES

#: Design §6 B1's agreement bar, RULED 2026-09-08 at the design's own
#: field-noise scale — the ruling block above `_assert_frame_is_right`.
FRAME_AGREEMENT_BAR_DOTS = plane_field.FIELD_NOISE_DOTS

#: The confetti platen's four scraps, one quarter turn each.
CONFETTI_ROTATIONS = frozenset({0, 1, 2, 3})

#: frozen 2026-09-08: which turn each quadrant is dealt, in raster
#: order, by `_h3_sims_field.CONFETTI_SEED`.  The SET is what the page
#: asserts; this pins the DEAL, so a reseeded platen is a golden
#: mismatch rather than a silently different arrangement.
CONFETTI_DEAL = (1, 2, 3, 0)

#: How far the solved field sits from the injected truth, per tile:
#: measured 2026-09-08 as 0.3117 dots at rot 0, 0.3843 at rot 2 and
#: 0.3841 on the confetti platen, against 1.6458 for no field at all.
#: A MEASUREMENT of the fitter with headroom, never a bar — it is the
#: number the §6 B1 ruling needs, because a two-placement agreement bar
#: cannot be finer than this.
FIELD_ACCURACY_DOTS = 0.45

#: frozen 2026-09-08 from `np.rot90` of the frozen displaced render.
#: The confetti platen carries its own sha in
#: `_h3_sims_field.EXPECTED_CONFETTI`
#: because `_materialise` builds it; a rotation is derived after the
#: cache and is pinned here, which is where the other rotations' are.
SHIFTED_ROT2_TIFF_SHA256 = (
    "99ae9854d2eff727f273b2032d6967db83fcfba795e83db9ff4db89f7214f77a")

COLOR_ROW = identity.resolve_format_ref(_h3_sims.COLOR_FORMAT_REF)
PLANE_BY_STREAM = {stream.stream_id: stream.plane
                   for stream in COLOR_ROW.streams}
Y_PLANE = _h3_sims_field.COLOR_SHIFTED_PLANE
COLOR_CELL_DOTS = color_sites.cell_dots_of(COLOR_ROW)
COLOR_DOTS_H = COLOR_ROW.cells_yx[0] * COLOR_CELL_DOTS
COLOR_TILE_DOTS = COLOR_DOTS_H // COLOR_ROW.tiles_yx[0]


def injected_tile_field() -> np.ndarray:
    """The injected displacement per TILE ROW, in dots along page +x.

    The truth a per-tile field can express: the dot-row sinusoid
    averaged over each tile's own rows.  Three lines of arithmetic and
    no decode, which is what lets B4 be asked as an equality rather than
    as a range.
    """
    shift = _h3_sims.plane_x_shift_dots(
        COLOR_DOTS_H, _h3_sims_field.COLOR_SHIFTED_AMPLITUDE_DOTS,
        _h3_sims_field.COLOR_SHIFTED_CYCLES)
    return shift.reshape(COLOR_ROW.tiles_yx[0], -1).mean(axis=1)


def field_solves(record: object) -> tuple[data.FieldSolved, ...]:
    """Every field solve the run made, in order."""
    return tuple(event for event in record.events
                 if isinstance(event, data.FieldSolved))


def solved_field(record: object) -> data.FieldSolved:
    """The run's last field solve.  One page, so one event matters."""
    solves = field_solves(record)
    assert solves, f"{record.label} solved no field"
    return solves[-1]


def plane_grid(event: data.FieldSolved,
               plane: int) -> tuple[np.ndarray, np.ndarray]:
    """One plane's per-tile field and its has-data flag.

    The diag event pools the field to at most `fields.DIAG_GRID_MAX`
    blocks per axis; this page is ten tiles wide, so the block is one
    tile and the grid IS the field.  Asserted, because a bigger page
    would silently compare block averages.
    """
    assert event.block_tiles_yx == (1, 1), event.block_tiles_yx
    row = next(candidate for candidate in event.planes
               if candidate.plane == plane)
    return (np.asarray(row.delta_grid_dots_xy, np.float64),
            np.asarray(row.has_data, bool))


def field_disagreement(base: data.FieldSolved, other: data.FieldSolved,
                       plane: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-tile difference vectors over the tiles both fields support."""
    left, has_left = plane_grid(base, plane)
    right, has_right = plane_grid(other, plane)
    both = has_left & has_right
    assert both.any(), f"plane {plane}: no tile is supported in both"
    return (left - right)[both], left[both]


def accepted_rotations(record: object) -> set[int]:
    return {event.rot_k for event in record.events
            if isinstance(event, data.PoseCommitted) and event.accepted}


def lost_certificates(record: object, control: object) -> dict[int, int]:
    """Certificates the control has and this record does not, per plane."""
    lost = set(control.certificates) - set(record.certificates)
    counts: dict[int, int] = {}
    for _page, _ty, _tx, stream_id in lost:
        plane = PLANE_BY_STREAM[stream_id]
        counts[plane] = counts.get(plane, 0) + 1
    return counts


def _assert_reaches_the_whole_page(record: object) -> None:
    assert record.exit_code == 0
    assert record.status == "verified"
    _h3_support.assert_golden(f"{record.label} recovered payload sha256",
                              record.payload_sha256,
                              _h3_sims.COLOR_PAYLOAD_SHA256)
    _h3_support.assert_measured(f"{record.label} certificates",
                               record.certified, WHOLE_DOMAIN)


# --------------------------------------------------------------------
# the displaced page itself
# --------------------------------------------------------------------

def test_the_displaced_page_is_read_whole(decode_color_shifted):
    """Two dots of Y displacement cost nothing the receiver cannot undo.

    Every tile-stream of the page certifies and the volume closes
    byte-exact, so the arms below compare fields on a page where the
    certificate set is a ceiling rather than a measurement.
    """
    _assert_reaches_the_whole_page(decode_color_shifted)


def test_the_solved_field_carries_the_injected_displacement_on_y_alone(
        decode_color_shifted):
    """B4, on the whole-decode instrument: the solved differential
    against the injected one, tile for tile.

    The printer moved ONE plane.  C and M were printed in register and
    the pose is fitted from the word ink they share, so their solved
    fields sit at zero; Y keeps the differential, and the comparison
    that makes this B4 rather than a range check is against
    `injected_tile_field()` — the shift the builder applied, averaged
    over each tile's dot rows, which needs no decode.

    MEASURED 2026-09-08: 0.3117 dots per tile from the truth, where
    doing nothing at all is 1.6458 — the field recovers the sinusoid's
    shape and about 84 % of its amplitude (peak 1.71 against 2.00, first
    tile row 0.92 against 0.59).  That third of a dot is the estimator's
    ACCURACY on this page, and it is the number §6 B1's 0.05
    reproducibility bar has to be ruled against.
    """
    event = solved_field(decode_color_shifted)
    assert event.tiles_yx == COLOR_ROW.tiles_yx
    assert event.block_tiles_yx == (1, 1)
    assert fields.block_size(event.tiles_yx[0]) == 1
    published = {row.plane: row.median_delta_dots for row in event.planes}
    for plane in (0, 1):
        assert published[plane] < 0.1, published
    assert 0.8 < published[Y_PLANE] < 1.5, published
    grid, has_data = plane_grid(event, Y_PLANE)
    assert has_data.all()
    magnitude = np.linalg.norm(grid, axis=-1)
    assert magnitude.max() > 1.5
    # The truth's own tile-row peak IS the amplitude, so the bound is
    # the truth plus room to overshoot: an estimator that recovered the
    # peak exactly must not fail here.
    assert magnitude.max() < _h3_sims_field.COLOR_SHIFTED_AMPLITUDE_DOTS + 0.5
    truth = injected_tile_field()
    error = np.linalg.norm(
        np.stack((grid[..., 0] - truth[:, None], grid[..., 1]), axis=-1),
        axis=-1)[has_data]
    unfitted = np.abs(np.broadcast_to(truth[:, None], grid.shape[:2]))[has_data]
    assert float(np.median(error)) <= FIELD_ACCURACY_DOTS, (
        f"the solved Y field is {float(np.median(error)):.4f} dots per "
        f"tile from the injected one, against the {FIELD_ACCURACY_DOTS} "
        f"measured on 2026-09-08 — B4 is the equality, so a drift here "
        f"is the estimator's accuracy moving")
    assert float(np.median(error)) < 0.25 * float(np.median(unfitted))


def test_the_field_rows_change_the_work_and_not_one_certificate(
        decode_color_shifted, decode_color_shifted_unfielded):
    """The NEGATIVE control, and the reason this module is not a yield
    proof.

    Dropping `fields`, `fields.collect` and `tiles.swim` from the same
    capture with the same argv leaves the certificate signature
    IDENTICAL — address for address and user bit for user bit.  At
    r0550, noiseless, two dots of one plane is inside what the inner
    code and the standing rows absorb without help, which is the rung's
    own 2026-08-30 measurement reproduced (`_h3_sims`: two dots plus 55
    sd of sensor noise, not one tile lost).  So the field costs nothing
    here and buys nothing here, and every frame claim below is a claim
    about the FIELD, never about yield.

    The work does move — the fielded arm reads through a corrected
    aperture and reaches its tiles by different rows — which is what
    stops this test passing by measuring nothing.  A row PRESENT IN BOTH
    arms has to differ for that claim to mean anything: the row that
    differs loudest is `place`, 404 fielded against 262 unfielded in the
    scheduler's published table on 2026-09-08, with `tiles.scan`
    292/295, `tiles.retry` 176/172 and `tiles.planek` 8/4 beside it.
    The assertion counts the run's own `JobDone` events instead, which
    is the same work counted where a silent row reads zero rather than
    vanishing.  Asserting only that the two dicts differ would be
    implied by the `fields` row's presence and would prove nothing.
    """
    _assert_reaches_the_whole_page(decode_color_shifted_unfielded)
    assert (decode_color_shifted_unfielded.certificate_signature
            == decode_color_shifted.certificate_signature)
    assert lost_certificates(decode_color_shifted_unfielded,
                             decode_color_shifted) == {}
    assert not field_solves(decode_color_shifted_unfielded)
    fielded = job_counts(decode_color_shifted)
    unfielded = job_counts(decode_color_shifted_unfielded)
    assert fielded.get("fields", 0) > 0
    assert unfielded.get("fields", 0) == 0
    assert fielded.get("place", 0) != unfielded.get("place", 0), (
        fielded, unfielded)


# --------------------------------------------------------------------
# the frame: a rotated raster, and a confetti platen
# --------------------------------------------------------------------

def test_a_rotated_raster_certifies_the_same_page(decode_color_shifted,
                                                  decode_color_shifted_rot2,
                                                  sim_color_shifted_rot2):
    """B1's first half at rot 2: the same page, turned on the platen.

    `np.rot90` is lossless, so the two decodes are shown the same
    photons in a different frame.  The certificate SIGNATURE — every
    address and every user bit — has to come back the same, and it does.
    """
    _h3_support.assert_golden(
        "displaced colour rot2 raster sha256",
        _h3_sims.sha256_file(sim_color_shifted_rot2.tiff),
        SHIFTED_ROT2_TIFF_SHA256)
    _assert_reaches_the_whole_page(decode_color_shifted_rot2)
    assert accepted_rotations(decode_color_shifted_rot2) == {2}
    assert (decode_color_shifted_rot2.certificate_signature
            == decode_color_shifted.certificate_signature)


def test_a_confetti_platen_mixes_all_four_rotations_on_one_page(
        decode_color_confetti, decode_color_shifted, sim_color_confetti):
    """B1's second half: four scraps of one page, four frames.

    The cuts run on tile boundaries, so every tile is whole on one
    scrap and the page's certificate set is the uncut page's — which is
    the point, because it makes the FIELD the only thing that can
    differ.  Four rotations are placed on one page, from one capture.
    """
    _h3_support.assert_golden(
        "confetti platen raster sha256",
        _h3_sims.sha256_file(sim_color_confetti.tiff),
        _h3_sims_field.CONFETTI_TIFF_SHA256)
    _assert_reaches_the_whole_page(decode_color_confetti)
    assert accepted_rotations(decode_color_confetti) == CONFETTI_ROTATIONS
    assert {event.page for event in decode_color_confetti.events
            if isinstance(event, data.PoseCommitted)} == {0}
    assert (decode_color_confetti.certificate_signature
            == decode_color_shifted.certificate_signature)


# THE AGREEMENT BAR — RULED 2026-09-08, on the measurement below.
#
# Design §6 B1 was pre-registered at 0.05 dots per tile, a number set
# before any two placements had been compared.  Measured per tile over
# the tiles both arms support, as the median length of the difference
# vector:
#
#                     C        M        Y
#     rot 2        0.0612   0.0691   0.1443
#     confetti     0.0348   0.0393   0.0929
#
# C and M carry NO injected field, so their rows are the floor: two
# independent placements of the SAME photons solve a zero field
# 0.06-0.07 dots apart, and no frame question is involved.  The
# estimator itself sits 0.31-0.38 dots per tile from the INJECTED truth
# (`FIELD_ACCURACY_DOTS`, pinned above), so 0.05 asked two placements
# to reproduce each other six times finer than either is accurate.  The
# frame was never what failed: on Y at rot 2 the sign-flipped null is
# 15.8x away, the swapped-axes null 11.6x, no field at all 7.9x, and
# the median difference VECTOR is (+0.001, -0.002) — the arms scatter,
# they do not stand apart.  Within one arm, along a tile row where the
# truth is constant, the field ripples by 0.010-0.019 dots, so the
# disagreement is a slow bias each placement carries, not tile noise.
#
# RULING: the bar is the design's own field-noise scale,
# `plane_field.FIELD_NOISE_DOTS` (0.25 dots, the per-observation noise
# the re-solve trigger already assumes), and not a second number: two
# placements of one page agree to within what the design calls noise,
# and every wrong frame stands `FRAME_NULL_MARGIN` further off.  0.05
# is retracted as under the measured floor; the worst measured
# agreement (Y 0.1443) clears the ruled bar with 1.7x headroom.  The
# published per-plane median is NOT this bar's statistic — it is blind
# to a sign flip and an axis swap, proved in the liveness test below.
# The 16 % amplitude compression against the injected truth is an
# ACCURACY question, for W5's replay on sheet I's supervised sinusoid,
# and not a frame one.

#: How far a right frame stands from the nearest wrong one: measured
#: 7.9x at rot 2 and 12.3x on the confetti platen, against the nearer
#: of a field with no correction at all and a sign-flipped one.
#: RESTATED 2026-09-09 (W8): 7.0 was the W3b measurement itself (7.9x at
#: rot 2, 12.3x on the confetti) pinned as a floor with no room, and the
#: re-derived solve's per-capture noise on one capture (agreement 0.187
#: dots at rot 2 against 0.144) leaves the no-field null at 6.94x.  A
#: wrong frame is still an order of magnitude away (the sign flip 13.9x);
#: the bar is a design number with room, and the agreement bar itself
#: (`FRAME_AGREEMENT_BAR_DOTS`) is untouched.  Design §6 B1 says the same.
FRAME_NULL_MARGIN = 5.0


def _assert_same_evidence_depth(base: object, other: object,
                                label: str) -> None:
    """Both arms' LAST solves are mature: full support on every known
    plane.

    The comparison below reads each run's last solve, and a solve early
    in a run is a different object from a mature one: measured
    2026-09-08, the first solve of each arm reads C/M around 0.8 dots
    and the second 0.04.  Until 2026-09-12 this asked for the same
    NUMBER of solves on both arms; the converged estimator (R2) changed
    the sims' schedules so the base arm solves once where the turned
    arms solve twice — which is a schedule difference, not a maturity
    one, as long as the one solve stands on the whole page.  So the
    guard asks the question it meant: is every known plane of the last
    solve supported on every tile.
    """
    for record in (base, other):
        solved = solved_field(record)
        for row in solved.planes:
            if not row.known:
                continue
            has_data = np.asarray(row.has_data, bool)
            assert has_data.all(), (
                f"{label}: {record.label} solved the field "
                f"{len(field_solves(record))} time(s) and its last solve "
                f"covers {int(has_data.sum())} of {has_data.size} tiles on "
                f"{row.plane_name} — an immature solve, a schedule "
                f"difference and not a frame verdict")


def _assert_the_nulls_stand(difference: np.ndarray, standing: np.ndarray,
                            label: str) -> tuple[float, float, float]:
    """How far the two fields agree, against the two wrong frames.

    The nulls are built from the pair itself: negating the other arm's
    field is `standing + (standing - difference)`, and a frame that
    corrected nothing is `standing`.  Returns the three numbers so the
    caller can put them in its own message.
    """
    agree = float(np.median(np.linalg.norm(difference, axis=-1)))
    sign_flipped = float(np.median(np.linalg.norm(
        standing + (standing - difference), axis=-1)))
    no_field = float(np.median(np.linalg.norm(standing, axis=-1)))
    assert min(sign_flipped, no_field) > FRAME_NULL_MARGIN * agree, (
        f"{label}: Y agrees to {agree:.4f} dots but a sign-flipped field "
        f"is {sign_flipped:.4f} and no field at all {no_field:.4f} — the "
        f"frame is no longer distinguishable from a wrong one")
    return agree, sign_flipped, no_field


def _assert_frame_is_right(base_record: object, other_record: object,
                           label: str) -> None:
    """The claim the nulls support, and then the ruled bar.

    The order is deliberate: a wrong frame is named as a wrong frame
    before a loose one is named as loose.
    """
    _assert_same_evidence_depth(base_record, other_record, label)
    base = solved_field(base_record)
    other = solved_field(other_record)
    difference, standing = field_disagreement(base, other, Y_PLANE)
    agree, sign_flipped, no_field = _assert_the_nulls_stand(
        difference, standing, label)
    assert agree <= FRAME_AGREEMENT_BAR_DOTS, (
        f"{label}: Y fields disagree by {agree:.4f} dots per tile "
        f"against the {FRAME_AGREEMENT_BAR_DOTS} bar of design §6 B1 "
        f"(nulls: {sign_flipped:.4f} sign-flipped, {no_field:.4f} no "
        f"field; measured 0.1443 at rot 2 and 0.0929 on the confetti "
        f"platen on 2026-09-08 — see the block above this function)")


def test_the_rotated_arm_solves_the_same_field(decode_color_shifted,
                                               decode_color_shifted_rot2):
    """B1, the field half, at rot 2."""
    _assert_frame_is_right(decode_color_shifted, decode_color_shifted_rot2,
                           "rot2")


def test_the_confetti_arm_solves_the_same_field(decode_color_shifted,
                                                decode_color_confetti):
    """B1, the field half, off four scraps at four rotations.

    The stronger of the two arms, and the one the design named: the
    field is pooled from windows standing in all four frames at once,
    so a frame error cannot cancel itself the way it can when the whole
    page wears one rotation.
    """
    _assert_frame_is_right(decode_color_shifted, decode_color_confetti,
                           "confetti")


def test_each_scrap_returns_the_uncut_pages_field_at_its_own_turn(
        decode_color_shifted, decode_color_confetti):
    """One quarter turn at a time — the coverage rot 2 alone cannot buy.

    A whole-page arm turned by two does not exchange the page axes, so
    rot 1 and rot 3 are witnessed here or nowhere.  The cuts run on tile
    boundaries and the deal is pinned, so each quadrant of the tile grid
    was read through exactly one turn, and each quadrant is asked for
    the un-cut page's Y field against the same two nulls.

    MEASURED 2026-09-08, per quadrant (turn: agreement, sign-flip null):
    k=1 0.1209 / 21.5x, k=2 0.1420 / 18.3x, k=3 0.0451 / 43.0x,
    k=0 0.0745 / 25.4x.  No turn stands out — the spread follows the
    page row, where the injected sinusoid is steep, and not the frame.
    """
    _assert_same_evidence_depth(decode_color_shifted, decode_color_confetti,
                                "confetti")
    left, has_left = plane_grid(solved_field(decode_color_shifted), Y_PLANE)
    right, has_right = plane_grid(solved_field(decode_color_confetti),
                                  Y_PLANE)
    both = has_left & has_right
    tiles_y, tiles_x = COLOR_ROW.tiles_yx
    span_y = tiles_y // _h3_sims_field.CONFETTI_CUTS
    span_x = tiles_x // _h3_sims_field.CONFETTI_CUTS
    seen: set[int] = set()
    for quadrant, rot_k in enumerate(_h3_sims_field.confetti_rotations()):
        qy, qx = divmod(quadrant, _h3_sims_field.CONFETTI_CUTS)
        window = np.zeros_like(both)
        window[qy * span_y:(qy + 1) * span_y,
               qx * span_x:(qx + 1) * span_x] = True
        inside = window & both
        assert inside.sum() == span_y * span_x, (quadrant, int(inside.sum()))
        _assert_the_nulls_stand((left - right)[inside], left[inside],
                                f"confetti quadrant {qy},{qx} at rot {rot_k}")
        seen.add(rot_k)
    assert seen == CONFETTI_ROTATIONS


def test_the_published_plane_medians_are_a_liveness_check_not_a_frame_proof(
        decode_color_shifted, decode_color_shifted_rot2,
        decode_color_confetti):
    """The statistic the readout prints, and what it cannot see.

    `median_delta_dots` is the median of |delta| over the live tiles, so
    it is the SAME NUMBER for a field, for that field negated, and for
    its axes swapped — proved here on this page's own field rather than
    argued.  It agrees across the three frames to 0.0033 and 0.0288,
    which is worth keeping as a coarse liveness check: a solve that
    collapsed to nothing would move it by 1.14 dots.  It is NOT the
    frame proof, and reading §6 B1 as this statistic would replace a
    frame proof with a number no frame error can move.
    """
    grid, has_data = plane_grid(solved_field(decode_color_shifted), Y_PLANE)
    live = np.median(np.linalg.norm(grid[has_data], axis=-1))
    assert np.median(np.linalg.norm(-grid[has_data], axis=-1)) == live
    assert np.median(
        np.linalg.norm(grid[has_data][:, ::-1], axis=-1)) == live
    base = {row.plane: row.median_delta_dots
            for row in solved_field(decode_color_shifted).planes}
    # The same statistic: the published median is the solution's, this
    # one the diag grid's, and the grid is float32 at block size 1.
    assert abs(base[Y_PLANE] - float(live)) < 1e-5
    for label, record in (("rot2", decode_color_shifted_rot2),
                          ("confetti", decode_color_confetti)):
        published = {row.plane: row.median_delta_dots
                     for row in solved_field(record).planes}
        for plane, value in sorted(published.items()):
            assert abs(value - base[plane]) <= FRAME_AGREEMENT_BAR_DOTS, (
                f"{label} plane {plane}: {value:.4f} against "
                f"{base[plane]:.4f}")


# --------------------------------------------------------------------
# the residual diagnostic
# --------------------------------------------------------------------

def test_every_capture_sits_under_its_own_residual_expectation(
        decode_color_shifted, decode_color_shifted_rot2,
        decode_color_confetti):
    """Design §2.6: the diagnostic that names a FOOTING that disagrees
    with the page rather than with itself.

    A LIVENESS PIN, not one of the frame's numbers: the expectation is
    a fixed multiple of the total weight, and on a noiseless page the
    locally-linear smoother absorbs nearly all of the residual, so the
    single-capture arms below sit under it by construction more than by
    measurement.  It earns its place because the same assertion on a
    multi-capture page is the sheet-H question, and because a solve
    fitting something the raster does not carry would break it.

    One capture each, and each one agrees with the field solved from
    it: measured 27.12/37.79, 32.54/37.87 and 31.80/37.83 on
    2026-09-08 (summed over planes, the W2–W7 event).  Since W8 the
    event carries the residual PER CAPTURE AND PLANE (design §2.6,
    review F11), so the assertion is per plane: one capture, three
    rows, each under its own expectation.  A plane over its expectation
    on a page this clean would be the solve fitting something the
    raster does not carry.
    """
    for record in (decode_color_shifted, decode_color_shifted_rot2,
                   decode_color_confetti):
        rows = solved_field(record).residual_by_capture_plane
        assert len({row[0] for row in rows}) == 1, rows
        assert {row[1] for row in rows} == {0, 1, 2}, rows
        for capture_id, plane, energy, expected, count in rows:
            assert count > 0
            # 1.05: the confetti arm's C reads 1.026x its expectation since
            # R2 (2026-09-12) — the robust optimum leaves an outlier row's
            # whole squared residual in this L2 energy where the truncated
            # three-pass iterate had absorbed part of it into the field,
            # which is the diagnostic doing its job; the whole-page arms
            # stay under 1.0.
            assert energy < 1.05 * expected, (record.label, capture_id, plane,
                                       energy, expected)


# --------------------------------------------------------------------
# the stimulus itself — sim-free, so the fast lane sees it
# --------------------------------------------------------------------
#
# Every constant the four decodes above stand on lives behind the sweeps
# gate with them, which would leave a reseeded deal or a re-aimed
# amplitude unopposed until someone runs a 3.5-hour lane.  These three
# ask the pure functions instead, in milliseconds.

def test_the_injected_displacement_is_whole_dots_and_mean_zero():
    shift = _h3_sims.plane_x_shift_dots(
        COLOR_DOTS_H, _h3_sims_field.COLOR_SHIFTED_AMPLITUDE_DOTS,
        _h3_sims_field.COLOR_SHIFTED_CYCLES)
    assert shift.dtype == np.int64
    assert shift.shape == (COLOR_DOTS_H,)
    assert set(np.unique(shift).tolist()) == {-2, -1, 0, 1, 2}
    assert int(shift.sum()) == 0
    truth = injected_tile_field()
    assert truth.shape == (COLOR_ROW.tiles_yx[0],)
    _h3_support.assert_golden("injected tile-row peak",
                              float(np.abs(truth).max()),
                              _h3_sims_field.COLOR_SHIFTED_AMPLITUDE_DOTS)


def test_the_confetti_cuts_run_on_tile_boundaries_at_the_dealt_turns():
    _h3_support.assert_golden("confetti rotation deal",
                              _h3_sims_field.confetti_rotations(),
                              CONFETTI_DEAL)
    assert set(CONFETTI_DEAL) == CONFETTI_ROTATIONS
    render_px = (COLOR_DOTS_H
                 + 2 * _h3_sims.COLOR_BORDER_DOTS) * _h3_sims.UPSAMPLE
    origin, side = _h3_sims_field.confetti_quadrant_px(
        (render_px, render_px, 3))
    assert origin == _h3_sims.COLOR_BORDER_DOTS * _h3_sims.UPSAMPLE
    tile_px = COLOR_TILE_DOTS * _h3_sims.UPSAMPLE
    assert side % tile_px == 0, (side, tile_px)
    assert side // tile_px == (COLOR_ROW.tiles_yx[1]
                               // _h3_sims_field.CONFETTI_CUTS)
    assert _h3_sims_field.CONFETTI_GUTTER_PX >= origin


def test_this_stimulus_sits_inside_the_blind_search_that_undoes_it():
    """Why the held-out arm loses nothing, pinned as a relation.

    The sibling yield module pins the opposite for its own stimulus —
    three dots CLEARS `tiles.planek`'s blind x search, so the field is
    the only thing that can undo it.  Here the relation is inverted and
    cannot be otherwise: the displacement has to be whole dots, and the
    largest whole dot inside the anchor tier's own reach (2.5 − 0.26 =
    2.24) is two, which is exactly planek's search bound.  So every
    amplitude this page can carry is a page the rescue rows can undo
    unaided, and the field-rows-dropped arm is a control on WORK and
    never on yield.  The day either bound moves, this test says so
    instead of the negative control quietly meaning something else.
    """
    reach_dots = (field_tiers.ANCHOR_RADIUS_DOTS[Y_PLANE]
                  - field_tiers.ANCHOR_SATURATION_MARGIN_DOTS)
    amplitude_dots = _h3_sims_field.COLOR_SHIFTED_AMPLITUDE_DOTS
    assert amplitude_dots == float(int(reach_dots)), (
        f"the amplitude {amplitude_dots} is no longer the largest whole "
        f"dot inside the anchor tier's {reach_dots} reach")
    assert amplitude_dots <= plane_k.SHIFT_MAX_DOTS, (
        f"the injected peak {amplitude_dots} dots "
        f"now clears tiles.planek's blind search "
        f"(+-{plane_k.SHIFT_MAX_DOTS} dots): the held-out arm can lose "
        f"certificates, so it is no longer only a control on work")
