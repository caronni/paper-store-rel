"""Existence proofs for the supplemental arms, against the arm-off control.

These run the real colour codec over a synthetic printed page built from
the colour sim's REAL emitted ground truth, so every tile carries real
content and can actually certify.  Three tiers see the identical region
inputs and the identical certificate frontier and differ ONLY in the
override, so a delta against ``off`` is the arm's and nothing else.

That control is the point.  v1 registered the same test as owed and never
ran it (COLOR-UPLIFT-MEASUREMENTS §10.6: "the +1 M is the u-a4b LANE's
add, not proven to be the ARM's ... the discriminating test is a u-lane
pair differing only in the override, and it is owed, not done").  The
first thing it caught here was a +6 that was NOT the arm but the ordinary
receiver's own certificate feedback re-fitting the region.

They are ORACLE-SWEEP gated because one tier is a full region derivation
over a 4x4-tile page and the standing slow lane has no room for four of
them.

WHAT REACHING A4b COST, recorded so nobody repeats the search.  Twenty
channel configurations were measured before the shape below was settled:

* Full contrast (the colour sim's own render: contrast 1.0, no noise) —
  every held-out NLL is exactly -0.0 and NO photometric arm can earn its
  gate.  COLOR-UPLIFT-MEASUREMENTS §5.4 states this outcome in advance;
  it is reproduced here, not discovered.
* Independent RGB channels (an identity CMY->RGB mix) — conditioning is
  provably VACUOUS: with no crosstalk a certified C and M carry no
  information about Y, so restricting the marginal to the consistent
  states cannot sharpen anything.  The fixture therefore carries a
  subtractive mix, which is what makes the question meaningful.
* Strong crosstalk (off-diagonal 0.75) — the opposite failure: the
  eight-state QDA then reads Y out of the correlated R and G directly,
  every tile certifies unconditionally, and there is no residue at all.
* A uniform starved plane at any strength — ``measure/uplift_cliff.py``
  scans Y from 0.20 to 0.50 and the codec steps from 0/16 to 16/16
  between 0.400 and 0.420, with conditioning moving NOTHING anywhere on
  the scan, the gated and ungated tiers alike.  A page at one tone puts
  every tile at the same point on the LDPC waterfall.
* Seeded per-tile jitter on the starved plane, meant to spread tiles
  across that cliff — the step stayed sharp.

So A4b is REACHED (it fits, adopts strata, conditions tens of thousands
of arity-2 marginals and changes the emitted evidence) and converts no
tile in any sim shape tried.  Its proof below is therefore the
unit-level one the charter allows: the arm measurably sharpens the
starved plane's evidence AT THE DECODER'S INPUT.  Converting that into a
certificate is a threshold event, and v1's own paper record says it is a
rare one — +1 tile on hp c3-cmy8 and +2 on xerox c2-cmy8 in full-lane
replays over thousands of tiles.

CORRECTION 2026-08-31 — CORNER HALF-CELL REMOVED.  Everything above was
measured through a fixture that aimed its sampler at cell CORNERS
instead of centres (``measure/uplift_fixture.py``'s ``region_windows``
lacked the ``+ 0.5`` that ``color_region.region_window`` composes).  At
this sim's geometry that is 3 px = 1.5 printed dots, and because the
sampler's aperture is ``round(0.7 * pitch_px)`` = 4 px the box straddled
the 2x2 cell junction evenly, so every plane read at exactly a QUARTER
of its true contrast: measured, the isolated-plane read was 31.5% cell
error with fitted contrast 0.073, against 0.002% and 0.292 once the
points were moved to centres.  The old record above is kept as written;
these are the corrections to it.

* The starved-plane cliff was NOT at 0.400-0.420.  That was the
  handicap.  Re-scanned after the fix, the codec certifies 48/48 from
  y_scale 0.220 up and the step sits at 0.210-0.220; the old A4b channel
  at 0.40 now leaves NO residue at all.  ``A4B_CHANNEL`` therefore moved
  to 0.15, which reproduces the old structure exactly (32 ordinary, 16
  residue).
* THE NEGATIVE STANDS, and it is now a much stronger statement.
  ``measure/uplift_cliff.py`` re-run over the real band 0.100-0.220
  (13 points) puts the ``a4b`` column EQUAL to the ``off`` column at
  every single point, gated and ungated alike — conditioning converts
  nothing anywhere, exactly as before, but now measured where a residue
  actually exists rather than in a regime the defect had flattened.
* The unit-level claim also stands: conditioning still sharpens the
  starved plane's evidence at the decoder's input, 0.834808 ->
  0.837280 (it was 0.764877 -> 0.770691 through the defect).
* A3 was NOT handicapped into its result either — it gains 29 tiles
  over a zero control after the fix, against 28 before.

REBUILT 2026-09-12 — THE STARVED PLANE IS NOW OUT OF REGISTER (the
lead's ruling, PAGE-FIELD-DESIGN §7.1's A4b debt).  Every A4b number
above and below 2026-09-07 was measured beside a corrected arm the
fixture never asked for: the always-on {1, y} registration residual
§2.2 of that design retired.  When it went the arm's margin went to
exactly zero, because a page printed in perfect register gives
``build_region_inputs`` nothing to fit a second arm from.  The fixture
now carries the physical effect the arm's own case names — the starved
plane printed 2 px = one printed dot = a THIRD OF A CELL along x, and
the page's own field handed in through the door ``plugins/uplift.py``
hands production's (``Channel.starved_shift_px``,
``uplift_fixture.plane_fields``).  The field is the INJECTED one, not a
solved one: the displacement is a constant this fixture wrote, so the
exact answer is known and the arm under test stays A4b rather than the
estimator, which has its own bars on its own stimuli.

* The corrected arm is present AND WINS the region's registration gate,
  so the conditioning strata are fitted on the features it selected.
* The stratum that reaches the starved plane's emitted cells — (plane 2,
  pattern 3) — passes its held-out gate by -0.0208 where it failed by
  +0.0006 in register.
* THE MARGIN IS POSITIVE AGAIN: +143 cells of 65,536 at the channel's own
  y_scale 0.15, and +680 / +387 / +37 at 0.17 / 0.19 / 0.21 — the same
  sign across the band, not one lucky point.  The former strict xfail is
  a pin again.
* THE TILE-CONVERSION NEGATIVE STILL STANDS: 0 of the 16 residue streams
  on both sides at 0.15, and the ``off`` and ``a4b`` columns equal at
  every scanned point above (2 and 2 at 0.21).  Unchanged verdict, now
  measured on a fixture that poses the question.
* The ordinary frontier does not move: 32 certificates and 16 residue
  streams in register and out of it.
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from holo.receiver.lib import page_map
from holo.receiver.lib.geometry import TILE_CELLS
from holo.receiver.plugins import color_arms, color_region, uplift
from holo.receiver.tests import _h3_sims, _h3_support

sys.path.insert(0, str(_h3_support.WORKTREE_ROOT / "measure"))

probe = pytest.importorskip("uplift_existence")
fixture = pytest.importorskip("uplift_fixture")

# A3's channel: a gain and offset constant WITHIN a window and stepping
# between windows, which is the pathology the arm exists for. The
# amplitude is deliberately well ABOVE anything measured on paper — see
# the assertion on the fitted spread below, which reports both.
A3_CHANNEL = fixture.Channel(gain_sd=0.15, absorption=0.12, noise_sd=0.045)
#
# RE-MEASURED 2026-09-03 for the b8471fc re-key: the arm's gain fell
# 29 -> 8 and the ordinary frontier rose 15 -> 16.  Not a seam bug --
# both paths driven over one page agree exactly, tier gain 8 and
# prepared-job minted 8, set difference zero both ways — and not the
# arm, since nothing in src/holo/receiver/plugins moved.  The re-keyed page redrew
# which tiles sit just under the LDPC threshold where a per-window
# gain/offset re-fit can lift them.  The proof survives on its own terms
# (control gains ZERO, the 8 are disjoint from the frontier, the fit
# adopts, zero wrong below), so this is a re-pin; restoring the old
# strength means re-tuning A3_CHANNEL against the new page — a separate
# line and a user ruling.
A3_ORDINARY_CERTIFIED = 16
A3_ARM_GAIN = 8

# A4b's channel: two healthy planes certifying beside a starved third,
# which is sheet H's measured shape and the arm's own case.
#
# THE STARVED SCALE MOVED 0.40 -> 0.15 ON 2026-08-31: corner half-cell
# removed.  The fixture aimed its sampler at cell corners, so the
# sampler's 4 px box straddled the 2x2 cell junction and every plane read
# at a QUARTER of its true contrast.  With centres the isolated-plane
# read went 31.5% cell error -> 0.002%, so y_scale 0.40 no longer starves
# anything (it certifies 48/48, leaving the arm no residue at all) and
# the codec's cliff moved from 0.400-0.420 down to 0.210-0.220.  0.15
# sits in the new flat residue band and reproduced the OLD structure
# exactly — 32 ordinary certificates, 16 residue streams — so the arm
# faces the same question it faced before, at the strength that actually
# poses it now.  (That structure held until the b8471fc re-key redrew the
# page: 36 ordinary and 12 residue now, same channel, same band.  The
# residue is thinner but not gone, so the arm still faces the question.)
#
# AND THE STARVED PLANE IS NOW PRINTED OUT OF REGISTER, 2026-09-12 (the
# lead's ruling; PAGE-FIELD-DESIGN §7.1's A4b debt).  A4b is fitted
# BESIDE the registration arm, and until this date the fixture had no
# registration error in it at all: it inherited its second arm from the
# always-on {1, y} residual the design retired at W3, and when that went
# the margin went with it.  The displacement is the physical effect the
# arm's own case names — 2 px = one printed dot = a third of a cell on
# the starved plane, and the page's own field handed to
# `build_region_inputs` the way `plugins/uplift.py` hands production's.
# Measured: the corrected arm is present AND wins the registration gate,
# the stratum that reaches the starved plane's emitted cells — (plane 2,
# pattern 3) — goes from failing its held-out gate by +0.0006 to passing
# it by -0.0208, and the arm's margin is +143 cells of 65,536.
A4B_CHANNEL = fixture.Channel(gain_sd=0.0, absorption=0.30, noise_sd=0.075,
                              plane_scale=(1.0, 1.0, 0.15),
                              starved_shift_px=2)
# RE-MEASURED 2026-09-03 for the same re-key: 32 -> 36 ordinary
# certificates on the re-drawn page.  This one moved the arm's way (a
# larger certified population beside the starved plane); the residue and
# the two accuracies below are re-read from the same run.
#
# BACK TO 32, 2026-09-07 (W3a, the registration residual retired; ruled
# 2026-09-08).  This is the BASE arm's honest number and not a
# regression: the instrument calls `build_region_inputs` directly with
# no store and therefore no page field, so its ordinary arm now has no
# registration correction at all where it used to have the always-on
# {1, y} residual.  It is a faithful measurement of a real state —
# production's colour lane fires before `fields.collect` and `fields`
# have produced anything, and in that window there is no corrected arm
# either.  The A3 channel's own baseline is unchanged, so the effect is
# this stimulus's and not universal.
#
# STILL 32 with the displacement and the field, 2026-09-12: the starved
# plane is a third of a cell out of register AND read through the field
# that says so, and the ordinary frontier lands on the same 32 streams
# it did in register.  The arm faces the same question, over the same
# residue, beside a head that now has two arms.
A4B_ORDINARY_CERTIFIED = 32
# RE-MEASURED 2026-09-08 off the page-field line's one sweeps pass (W6
# landing), all four in one run through a runtime golden recorder.  The
# residue is the complement of the frontier on this 48-stream page, so
# 32 ordinary certificates leave 16 residue streams (the 2026-08-31
# structure again), and the residue's rows are 4 windows x 16,384 cells.
A4B_RESIDUE_STREAMS = 16
# THE MARGIN WAS EXACTLY ZERO between 2026-09-07 and 2026-09-12, and the
# mechanism was measured before the numbers were moved (probes under the
# session scratchpad, W2 tree against this one, code byte-identical on
# the whole conditioning path): the fixture handed no page field, so the
# corrected arm that W2 always synthesised from the {1, y} registration
# residual no longer existed (`RegionInputs.corrected` was None); the
# detector fit differed, the frontier moved 36 -> 32 and the residue
# 12 -> 16, and the ONE stratum that reaches the starved plane's emitted
# cells — (plane 2, pattern 3), fitted on 96 furniture cells and no
# certificate cell on either tree — landed on the wrong side of its
# held-out gate (+0.0006 against -0.0227 before).  Three strata still
# adopted, on planes and patterns that reach no emitted cell of plane 2,
# so the conditioned head changed plane 0 and left plane 2 untouched.
# W2's own code with `corrected` forced to None reproduced every number
# bit-exactly, so it was the fixture's state and not a code change: the
# always-on residual the design retired was what had been posing the arm
# its question here.
#
# RE-MEASURED 2026-09-12 ON THE REBUILT FIXTURE (the ablation is one
# `measure/uplift_existence.py` run per shift, everything else
# identical): with the starved plane printed a third of a cell out of
# register and the page's field handed in, the corrected arm exists and
# WINS the registration gate, (plane 2, pattern 3) passes its held-out
# gate by -0.0208 where it failed by +0.0006, and the arm reads +143
# cells of 65,536 right that the control reads wrong.  In register, on
# this same tree, the same run reads 52,736 for both arms — the zero
# above.  The arm still converts NO tile: certificates 0 of the 16
# residue streams on both sides, which is the measured negative the
# module docstring records and which the cliff scan puts everywhere.
A4B_ACCURACY_OFF = 0.76507568359375
A4B_ACCURACY_CONDITIONED = 0.7672576904296875
# the same margin in CELLS: +143 of 65,536 (50,140 -> 50,283, read off
# the ablation run 2026-09-12; the two accuracies above are these three
# numbers divided out, exactly)
A4B_CELLS_TOTAL = 65536
A4B_CELLS_CORRECT_OFF = 50140
A4B_CELLS_CORRECT_CONDITIONED = 50283


def test_the_fixture_aims_at_cell_centres_not_corners():
    """THE VALUE GUARD for the 2026-08-31 correction.

    `test_h3_plugins_sampling_geometry` proves the two PRODUCTION
    composers agree.  `test_h3_hygiene`'s pose gate bans the FORM this
    fixture's defect took — a hand-built pose — outright, so the three
    files that carried it cannot come back.  This is the third question,
    which neither of those asks: does the composed pose actually land on
    the ink `render` laid down?  A fixture can route through production
    and still hand it a placement that describes the wrong page.

    No sim needed: this is the fixture's geometry against the fixture's
    own raster, so it runs in the fast lane where a regression is cheap
    to see.
    """
    row, _geometry = fixture.format_row_and_geometry()
    channel = fixture.Channel()
    span = channel.tiles_side * TILE_CELLS // channel.windows_side
    for window in fixture.region_windows(row, channel):
        wy, wx = divmod(int(window.patch_ordinal), channel.windows_side)
        # `render` lays window (wy, wx)'s first cell as a PPC-sized block
        # starting here, so the cell's CENTRE is half a cell further on.
        block_y = fixture.MARGIN_PX + wy * span * fixture.PPC
        block_x = fixture.MARGIN_PX + wx * span * fixture.PPC
        expected = (block_y + 0.5 * fixture.PPC,
                    block_x + 0.5 * fixture.PPC)
        first = window.scan_points_yx[0]
        assert (float(first[0]), float(first[1])) == expected, (
            "the fixture is aiming at a cell CORNER: at this geometry "
            "that is half a cell = 1.5 printed dots, and the sampler's "
            f"{max(1, round(0.7 * fixture.PPC))} px aperture then "
            "averages the 2x2 cell junction evenly, so every plane "
            "reads at a quarter of its true contrast")


def _guard_cells(channel) -> np.ndarray:
    """A deterministic printed pattern with structure along x."""
    side = channel.tiles_side * TILE_CELLS
    ys, xs = np.indices((side, side), dtype=np.int64)
    inked = ((ys * 131 + xs * 17) % 5 == 0).astype(np.uint8)
    return np.repeat(inked[..., None], 3, axis=2)


def test_the_injected_field_says_where_the_starved_plane_really_printed():
    """THE VALUE GUARD for the 2026-09-12 rebuild.

    The fixture writes the starved plane's registration error twice: into
    the RENDER, as ink laid a whole number of pixels along x, and into the
    FIELD it hands `build_region_inputs`, in printed dots.  If those two
    ever disagree the arm being measured is no longer A4b — a field
    pointing where the ink is not starves the plane further, and a
    conditioning margin measured beside it means nothing.

    Both halves are read through production: the displacement of the
    sampler is `lib/page_map`'s own, off the fixture's real window pose,
    and the displacement of the ink is measured on the raster.  No sim
    needed, so this runs in the fast lane where a drift is cheap to see;
    the crosstalk is dropped for this one render so the starved plane's
    channel carries nothing but the starved plane.

    The two planes that print IN REGISTER are pinned here too, on both
    halves: the page publishes all three fields or none (`plugins/
    fields.py`'s `solve_job`), so C and M carry an explicit zero that
    must move neither their sampler nor their ink.
    """
    row, _geometry = fixture.format_row_and_geometry()
    channel = fixture.Channel(noise_sd=0.0, mix=probe.crosstalk_mix(0.0),
                              starved_shift_px=2)
    window = fixture.region_windows(row, channel)[0]
    offsets = color_region.field_offsets(
        fixture.plane_fields(row, channel), window.page_cells_yx)
    displaced = page_map.raster_points(
        window.scan_points_yx, window.page_linear,
        offsets[fixture.STARVED_PLANE], color_region.cell_dots_of(row))
    moved_px = displaced - np.asarray(window.scan_points_yx, np.float64)
    assert np.array_equal(np.unique(moved_px[:, 0]), np.zeros(1)), (
        "the displacement is along x alone, so the field may not move "
        "the sampler in y at all")
    assert np.array_equal(np.unique(moved_px[:, 1]),
                          np.full(1, float(channel.starved_shift_px))), (
        "the field must move the sampler by exactly the pixels the "
        "render moved the ink, whole and in the same direction")
    for plane, entry in enumerate(offsets):
        if plane == fixture.STARVED_PLANE:
            continue
        assert np.array_equal(entry, np.zeros_like(entry)), (
            "a plane that printed in register publishes a field that "
            "says so — zero delta, read at the pose itself")

    printed = _guard_cells(channel)
    still = fixture.render(printed, replace(channel, starved_shift_px=0),
                           None, None)
    moved = fixture.render(printed, channel, None, None)
    shift = channel.starved_shift_px
    low = fixture.MARGIN_PX
    high = low + channel.tiles_side * TILE_CELLS * fixture.PPC
    assert np.array_equal(
        still[low:high, low:high - shift, fixture.STARVED_PLANE],
        moved[low:high, low + shift:high, fixture.STARVED_PLANE]), (
        "the rendered starved plane is not the in-register one moved "
        f"{shift} px along x")
    for plane in range(3):
        if plane == fixture.STARVED_PLANE:
            continue
        assert np.array_equal(still[low:high, low:high, plane],
                              moved[low:high, low:high, plane]), (
            "and the planes that ARE in register may not move with it")


@pytest.fixture(scope="module")
def emitted_page(sim_color: _h3_sims.SimCapture):
    _h3_support.skip_unless_oracle_sweeps(
        "the supplemental-arm existence proofs")
    assert sim_color.emit_dir is not None
    row, geometry = fixture.format_row_and_geometry()
    return row, geometry, fixture.page_bits(
        Path(sim_color.emit_dir) / "page000_gt.npy", row)


def _tiers(emitted_page, channel, arms):
    row, geometry, bits = emitted_page
    gains, offsets = fixture.window_gains(channel)
    image = fixture.render(bits, channel, gains, offsets)
    # The page's standing field, exactly where production's comes from
    # (`plugins/uplift.py`: `store.page_plane_fields(page)` into the plan
    # and on into `build_region_inputs`). A channel that prints in
    # register hands None, which is what no field standing yet means.
    fields = fixture.plane_fields(row, channel)
    windows = fixture.region_windows(row, channel)
    streams = tuple(stream.stream_id for stream in row.streams)
    every = tuple((ty, tx, streams)
                  for ty in range(channel.tiles_side)
                  for tx in range(channel.tiles_side))
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        planes = fixture.plane_rasters(image, Path(tmp))
        frontier, _v, _i, _s = probe.run_tier(
            row, geometry, windows, planes, {}, every, probe.ARM_OFF,
            fields)
        residue = tuple(
            entry for entry in (
                (ty, tx, tuple(name for name in streams
                               if (0, ty, tx, name) not in frontier))
                for ty, tx, _s in every)
            if entry[2])
        for arm in arms:
            out[arm] = probe.run_tier(row, geometry, windows, planes,
                                      dict(frontier), residue, arm, fields)
    return row, geometry, bits, frontier, residue, out


def test_a3_certifies_tiles_the_arm_off_control_cannot(emitted_page):
    row, geometry, bits, frontier, residue, tiers = _tiers(
        emitted_page, A3_CHANNEL,
        (probe.ARM_OFF, color_arms.UPLIFT_ARM_A3))
    _h3_support.assert_measured("A3 channel ordinary certificates",
                                len(frontier), A3_ORDINARY_CERTIFIED)
    control = tiers[probe.ARM_OFF][0]
    armed = tiers[color_arms.UPLIFT_ARM_A3][0]
    assert len(control) == 0, (
        "the control re-fits the region with the frontier and gains "
        "nothing, so every certificate below is the arm's")
    _h3_support.assert_measured("A3 arm gain over the control",
                                len(armed) - len(control), A3_ARM_GAIN)
    verdict = tiers[color_arms.UPLIFT_ARM_A3][1]
    assert verdict.adopted and verdict.accepted_maps > 0
    # zero wrong is the only bar this arm has
    wrong = 0
    everything = dict(frontier)
    everything.update(armed)
    for ty in range(A3_CHANNEL.tiles_side):
        for tx in range(A3_CHANNEL.tiles_side):
            wrong += fixture.audit_certificate(
                row, geometry, everything, bits, 0, ty, tx)
    assert wrong == 0, f"{wrong} certified component bits disagree"


def test_a3_only_ever_adds_and_never_re_attempts_a_certified_address(
        emitted_page):
    _row, _geometry, _bits, frontier, residue, tiers = _tiers(
        emitted_page, A3_CHANNEL, (color_arms.UPLIFT_ARM_A3,))
    armed = tiers[color_arms.UPLIFT_ARM_A3][0]
    assert set(armed).isdisjoint(set(frontier)), (
        "THE SUPPRESSION PIN: monotone by construction means a certified "
        "(address, stream) is never offered to a supplemental tier")
    offered = {(0, ty, tx, name)
               for ty, tx, pending in residue for name in pending}
    assert set(armed) <= offered


def test_a4b_sharpens_the_starved_plane_beside_its_certified_siblings(
        emitted_page):
    row, _geometry, bits, frontier, residue, tiers = _tiers(
        emitted_page, A4B_CHANNEL,
        (probe.ARM_OFF, color_arms.UPLIFT_ARM_A4B))
    _h3_support.assert_measured("A4b channel ordinary certificates",
                                len(frontier), A4B_ORDINARY_CERTIFIED)
    _h3_support.assert_measured(
          "A4b residue streams",
          sum(len(entry[2]) for entry in residue), A4B_RESIDUE_STREAMS)
    verdict = tiers[color_arms.UPLIFT_ARM_A4B][1]
    assert verdict.reason == "region_gate_forced", (
        "a forced adoption may never be readable as one the standing "
        "three-way comparison granted")
    assert verdict.cells_arity2 > 0 and verdict.cert_cells > 0, (
        "this is A4b's own case: the residue's cells carry two certified "
        "siblings apiece")
    off_stack = tiers[probe.ARM_OFF][3]
    assert tiers[probe.ARM_OFF][2].corrected is not None, (
        "A4b IS FITTED BESIDE THE REGISTRATION ARM: the starved plane is "
        "printed out of register and the page's field says so, so "
        "`build_region_inputs` must have a second arm to fit")
    assert off_stack.adopted, (
        "and the corrected arm must WIN the region's held-out gate — the "
        "conditioning strata are fitted on the features it selected")

    _h3_support.assert_measured(
          "A4b cells (correct off, correct conditioned, total)",
          (probe.starved_cells_correct(tiers[probe.ARM_OFF], bits)[0],
           probe.starved_cells_correct(
               tiers[color_arms.UPLIFT_ARM_A4B], bits)[0],
           probe.starved_cells_correct(tiers[probe.ARM_OFF], bits)[1]),
          (A4B_CELLS_CORRECT_OFF, A4B_CELLS_CORRECT_CONDITIONED,
           A4B_CELLS_TOTAL))

    def accuracy(tier) -> float:
        correct, total = probe.starved_cells_correct(tier, bits)
        return correct / total

    off = accuracy(tiers[probe.ARM_OFF])
    conditioned = accuracy(tiers[color_arms.UPLIFT_ARM_A4B])
    assert off == pytest.approx(A4B_ACCURACY_OFF, abs=5e-6)
    assert conditioned == pytest.approx(A4B_ACCURACY_CONDITIONED, abs=5e-6)


def test_a4b_conditioning_sharpens_the_starved_plane(emitted_page):
    """The arm's claim, kept separate from its measurements above so a
    golden drift cannot hide behind it.

    THE PIN THIS WAS AN EXPECTED FAILURE FROM 2026-09-07 TO 2026-09-12:
    the fixture had no registration error in it, so the head had one arm
    and the stratum that reaches the starved plane's emitted cells missed
    its held-out gate by 0.0006.  The invariant it pins is the arm's
    whole claim — conditioning on prior-barrier certified siblings must
    sharpen the starved plane's marginal at the decoder's input — and the
    fixture now poses it the way the design says it should
    (PAGE-FIELD-DESIGN §7.1's A4b debt): a real sub-cell per-plane
    registration error, and the page's field handed in through the door
    production hands it through.
    """
    _row, _geometry, bits, _frontier, _residue, tiers = _tiers(
        emitted_page, A4B_CHANNEL,
        (probe.ARM_OFF, color_arms.UPLIFT_ARM_A4B))
    off, _total = probe.starved_cells_correct(tiers[probe.ARM_OFF], bits)
    conditioned, _total = probe.starved_cells_correct(
        tiers[color_arms.UPLIFT_ARM_A4B], bits)
    assert conditioned > off, (
        "conditioning on certified siblings must sharpen the starved "
        "plane's evidence at the decoder's input")
    _h3_support.assert_measured(
          "A4b sharpening margin in cells", conditioned - off,
          A4B_CELLS_CORRECT_CONDITIONED - A4B_CELLS_CORRECT_OFF)


def test_the_supplemental_tiers_write_no_standing_evidence(emitted_page):
    row, geometry, bits, frontier, residue, tiers = _tiers(
        emitted_page, A3_CHANNEL, (color_arms.UPLIFT_ARM_A3,))
    windows = fixture.region_windows(row, A3_CHANNEL)
    gains, offsets = fixture.window_gains(A3_CHANNEL)
    image = fixture.render(bits, A3_CHANNEL, gains, offsets)
    with tempfile.TemporaryDirectory() as tmp:
        planes = fixture.plane_rasters(image, Path(tmp))
        plan = uplift.UpliftPlan(
            arm=color_arms.UPLIFT_ARM_A3, page=0, capture_id="cap",
            level_index=0,
            lane_windows=tuple(
                uplift.LaneWindow(window, window.window_id[3], 0)
                for window in windows),
            planes=planes, certificates=dict(frontier), targets=residue,
            plane_fields=(None, None, None))
        result = uplift.uplift_job(row, geometry, plan)
    kinds = {type(fact).__name__ for fact in result.facts}
    assert kinds <= {"AttemptFact", "Certificate"}, sorted(kinds)
    assert "ColorEvidenceRow" not in kinds, (
        "the correction is transient: it reaches the decoder input and is "
        "then discarded, so no standing cell can carry it")
    assert result.cpu_s >= 0.0


def test_prepare_builds_a_plan_whose_job_certifies_through_the_row_seam(
        emitted_page, monkeypatch):
    # The sims never fire this row — its price puts it last and by then
    # the page is done — so the scheduler seam it will actually run
    # through on a real sheet has to be exercised deliberately.
    row, geometry, bits = emitted_page
    gains, offsets = fixture.window_gains(A3_CHANNEL)
    image = fixture.render(bits, A3_CHANNEL, gains, offsets)
    windows = fixture.region_windows(row, A3_CHANNEL)
    streams = tuple(stream.stream_id for stream in row.streams)
    every = tuple((ty, tx, streams)
                  for ty in range(A3_CHANNEL.tiles_side)
                  for tx in range(A3_CHANNEL.tiles_side))
    with tempfile.TemporaryDirectory() as tmp:
        planes = fixture.plane_rasters(image, Path(tmp))
        frontier, _v, _i, _s = probe.run_tier(
            row, geometry, windows, planes, {}, every, probe.ARM_OFF,
            None)
        by_ordinal = {int(window.patch_ordinal): window
                      for window in windows}
        wids = tuple(window.window_id for window in windows)
        store = SimpleNamespace(
            row=row, geometry=geometry,
            lane_page_windows=lambda *args: wids,
            window_cover_tiles=lambda wid: tuple(
                (0, ty, tx, "cap", 0) for ty, tx, _s in every),
            has_certificate=lambda key: key in frontier,
            window=lambda wid: SimpleNamespace(region_index=0),
            rgb_planes=lambda lane: planes,
            page_plane_fields=lambda page: (None, None, None),
            certificates=lambda: dict(frontier))
        monkeypatch.setattr(
            uplift.color_region, "region_window",
            lambda _store, wid: by_ordinal[wid[2]])
        job = uplift.prepare_uplift(
            store, ("cap", 0, 0, color_arms.UPLIFT_ARM_A3), uplift.STAGE_A3)
        assert job is not None
        result = job()
    minted = {(fact.page, fact.ty, fact.tx, fact.stream_id)
              for fact in result.facts if hasattr(fact, "user_bits")}
    assert minted.isdisjoint(set(frontier))
    _h3_support.assert_measured("prepared A3 job certificates", len(minted),
                                A3_ARM_GAIN)
    assert result.cpu_s > 0.0, (
        "per-tool accounting: this row owns a region derivation no other "
        "row's meter covers")


def test_prepare_refuses_before_any_pixel_when_there_is_no_residue(
        emitted_page):
    row, _geometry, _bits = emitted_page
    every_stream = {(0, ty, tx, stream.stream_id)
                    for ty in range(A3_CHANNEL.tiles_side)
                    for tx in range(A3_CHANNEL.tiles_side)
                    for stream in row.streams}
    empty = SimpleNamespace(row=row, lane_page_windows=lambda *a: ())
    assert uplift.prepare_uplift(
        empty, ("cap", 0, 0, color_arms.UPLIFT_ARM_A3),
        uplift.STAGE_A3) is None
    done = SimpleNamespace(
        row=row, lane_page_windows=lambda *a: ("w",),
        window_cover_tiles=lambda wid: tuple(
            (0, ty, tx, "cap", 0)
            for ty in range(A3_CHANNEL.tiles_side)
            for tx in range(A3_CHANNEL.tiles_side)),
        has_certificate=lambda key: key in every_stream)
    assert uplift.prepare_uplift(
        done, ("cap", 0, 0, color_arms.UPLIFT_ARM_A3),
        uplift.STAGE_A3) is None


def test_the_a3_channel_reports_its_own_amplitude(emitted_page):
    # HONESTY PIN. The channel is stated against the measured paper
    # window rather than described as realistic: on paper the fitted
    # per-window gain spread runs 0.016-0.086 (the uplift target's own
    # lane 0.0601). This synthetic sits an order of magnitude above it,
    # which is why the arm is unmistakable here and marginal there.
    row, geometry, bits, frontier, _residue, tiers = _tiers(
        emitted_page, A3_CHANNEL, (probe.ARM_OFF,))
    _gained, _verdict, inputs, stack = tiers[probe.ARM_OFF]
    from holo.receiver.plugins import color_photometry

    maps = color_photometry.fit_window_photometry(
        stack.selected.model, inputs.selection, inputs.row_tuple,
        stack.features, color_photometry.WindowPhotometryConfig())
    gain_spread, offset_spread, accepted, _refused = (
        probe.fitted_dispersion(maps.fits))
    assert accepted >= 2
    assert gain_spread > 0.086, (
        f"this channel is {gain_spread:.4f}, deliberately above every "
        f"per-window gain spread measured on paper")
