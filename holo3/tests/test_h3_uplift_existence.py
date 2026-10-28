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
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from holo3.lib.geometry import TILE_CELLS
from holo3.plugins import color_arms, uplift
from holo3.tests import _h3_sims, _h3_support

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
# arm, since nothing in holo3/plugins moved.  The re-keyed page redrew
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
A4B_CHANNEL = fixture.Channel(gain_sd=0.0, absorption=0.30, noise_sd=0.075,
                              plane_scale=(1.0, 1.0, 0.15))
# RE-MEASURED 2026-09-03 for the same re-key: 32 -> 36 ordinary
# certificates on the re-drawn page.  This one moved the arm's way (a
# larger certified population beside the starved plane); the residue and
# the two accuracies below are re-read from the same run.
A4B_ORDINARY_CERTIFIED = 36
A4B_RESIDUE_STREAMS = 12
# The two accuracies moved with the page as well, 2026-09-03:
# 0.834808 -> 0.805013 off, 0.837280 -> 0.805461 conditioned.  THE CLAIM
# STILL HOLDS — `conditioned > off` is the assertion that matters and it
# is still true — but the margin narrowed from +0.002472 to +0.000448,
# which is worth knowing before anyone reads this arm as comfortable.
A4B_ACCURACY_OFF = 0.805013
A4B_ACCURACY_CONDITIONED = 0.805461
# the same margin in CELLS, so the reader sees 22 of 49,152 rather than a
# ratio at 5e-6 (read off the run 2026-09-03; the review's draft figures
# were exactly five times these, so do not trust a number here that was
# not read off a run)
A4B_CELLS_TOTAL = 49152
A4B_CELLS_CORRECT_OFF = 39568
A4B_CELLS_CORRECT_CONDITIONED = 39590


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
    windows = fixture.region_windows(row, channel)
    streams = tuple(stream.stream_id for stream in row.streams)
    every = tuple((ty, tx, streams)
                  for ty in range(channel.tiles_side)
                  for tx in range(channel.tiles_side))
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        planes = fixture.plane_rasters(image, Path(tmp))
        frontier, _v, _i, _s = probe.run_tier(
            row, geometry, windows, planes, {}, every, probe.ARM_OFF)
        residue = tuple(
            entry for entry in (
                (ty, tx, tuple(name for name in streams
                               if (0, ty, tx, name) not in frontier))
                for ty, tx, _s in every)
            if entry[2])
        for arm in arms:
            out[arm] = probe.run_tier(row, geometry, windows, planes,
                                      dict(frontier), residue, arm)
    return row, geometry, bits, frontier, residue, out


def test_a3_certifies_tiles_the_arm_off_control_cannot(emitted_page):
    row, geometry, bits, frontier, residue, tiers = _tiers(
        emitted_page, A3_CHANNEL,
        (probe.ARM_OFF, color_arms.UPLIFT_ARM_A3))
    _h3_support.assert_golden("A3 channel ordinary certificates",
                              len(frontier), A3_ORDINARY_CERTIFIED)
    control = tiers[probe.ARM_OFF][0]
    armed = tiers[color_arms.UPLIFT_ARM_A3][0]
    assert len(control) == 0, (
        "the control re-fits the region with the frontier and gains "
        "nothing, so every certificate below is the arm's")
    _h3_support.assert_golden("A3 arm gain over the control",
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
    _h3_support.assert_golden("A4b channel ordinary certificates",
                              len(frontier), A4B_ORDINARY_CERTIFIED)
    _h3_support.assert_golden(
        "A4b residue streams",
        sum(len(entry[2]) for entry in residue), A4B_RESIDUE_STREAMS)
    verdict = tiers[color_arms.UPLIFT_ARM_A4B][1]
    assert verdict.reason == "region_gate_forced", (
        "a forced adoption may never be readable as one the standing "
        "three-way comparison granted")
    assert verdict.cells_arity2 > 0 and verdict.cert_cells > 0, (
        "this is A4b's own case: the residue's cells carry two certified "
        "siblings apiece")

    def accuracy(tier) -> float:
        _gained, _verdict, inputs, stack = tier
        rows = uplift._transient_rows(inputs, stack)
        total = 0
        correct = 0
        for _ordinal, cells, values, _loss in rows:
            truth = bits[cells[:, 0], cells[:, 1], 2]
            total += truth.size
            correct += int(
                ((values[:, 2] > 0.0).astype(np.uint8) == truth).sum())
        return correct / total

    def correct_cells(tier) -> tuple[int, int]:
        _gained, _verdict, inputs, stack = tier
        total = correct = 0
        for _ordinal, cells, values, _loss in uplift._transient_rows(
                inputs, stack):
            truth = bits[cells[:, 0], cells[:, 1], 2]
            total += truth.size
            correct += int(
                ((values[:, 2] > 0.0).astype(np.uint8) == truth).sum())
        return correct, total

    _h3_support.assert_golden(
        "A4b cells (correct off, correct conditioned, total)",
        (correct_cells(tiers[probe.ARM_OFF])[0],
         correct_cells(tiers[color_arms.UPLIFT_ARM_A4B])[0],
         correct_cells(tiers[probe.ARM_OFF])[1]),
        (A4B_CELLS_CORRECT_OFF, A4B_CELLS_CORRECT_CONDITIONED,
         A4B_CELLS_TOTAL))

    off = accuracy(tiers[probe.ARM_OFF])
    conditioned = accuracy(tiers[color_arms.UPLIFT_ARM_A4B])
    assert off == pytest.approx(A4B_ACCURACY_OFF, abs=5e-6)
    assert conditioned == pytest.approx(A4B_ACCURACY_CONDITIONED, abs=5e-6)
    assert conditioned > off, (
        "conditioning on certified siblings must sharpen the starved "
        "plane's evidence at the decoder's input")


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
            planes=planes, certificates=dict(frontier), targets=residue)
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
            row, geometry, windows, planes, {}, every, probe.ARM_OFF)
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
    _h3_support.assert_golden("prepared A3 job certificates", len(minted),
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
    from holo3.plugins import color_photometry

    maps = color_photometry.fit_window_photometry(
        stack.selected.model, inputs.selection, inputs.row_tuple,
        stack.features, color_photometry.WindowPhotometryConfig())
    gain_spread, offset_spread, accepted, _refused = (
        probe.fitted_dispersion(maps.fits))
    assert accepted >= 2
    assert gain_spread > 0.086, (
        f"this channel is {gain_spread:.4f}, deliberately above every "
        f"per-window gain spread measured on paper")
