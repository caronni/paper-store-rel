"""Existence proof for `tiles.planek`, against the arm-off control.

The channel is the MEASURED disease: one plane's ink displaced in x over
a column band of the page (`measure/planek_fixture`).  e033 measured that
object on the AltaLink as a yellow x-registration sinusoid, 0.83 dot peak
and ~100 mm period, and `measure/yask` §4.2 showed it is what separates a
live column from a dead one — the two populations peak at DIFFERENT
sampling offsets, so one page-global correction cannot serve both.  The
colour lane's own per-plane residual is a function of page-y, which is
exactly why a displacement that varies with page-X survives it.

Three tiers see the identical frontier and the identical residue:

    off      the ordinary colour head, re-run at the same 150-iteration
             budget with the frontier it did not have the first time
    planek   `plane_k.planek_job`, unchanged
    null     the same evidence decoded at the WRONG address

The control is the point, and it is not decoration: at a slightly
smaller displacement the control recovers the whole residue on its own,
which is precisely the kind of gain a careless probe would have banked
as the arm's.

The row is PLANE-GENERAL, so the proof is run for all three planes.
Yellow off blue is the measured case; cyan off red and magenta off green
are the same arithmetic on a different column and take the same code
path.

ORACLE-SWEEP GATED, for `test_h3_uplift_existence.py`'s reason exactly:
each tier is a full region derivation plus a residue of heavy decodes
over a 4x4-tile page, and the standing slow lane has no room for
several of them.  The one test here that costs nothing — the run-scale
null, read off a decode the slow lane already makes — stays in the slow
lane.
"""

from __future__ import annotations

import sys
import tempfile
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from holo.receiver import data
from holo.receiver.data import AttemptFact, Certificate
from holo.receiver.lib.geometry import TILE_CELLS
from holo.receiver.plugins import plane_k
from holo.receiver.tests import _h3_sims, _h3_support

sys.path.insert(0, str(_h3_support.WORKTREE_ROOT / "measure"))

probe = pytest.importorskip("planek_existence")
fixture = pytest.importorskip("planek_fixture")

Y_PLANE = 2

# The ordinary path's own outcome on this channel: every tile addressed
# and certified in the two undisplaced planes, the target plane certified
# on the clean half of the page and nowhere on the band.
ORDINARY_FRONTIER = 40
CLEAN_TARGET_CERTIFIED = 8
BAND_TARGET_CERTIFIED = 0
TARGET_RESIDUE = 8

# The verdict.  The control gains NOTHING from the same frontier; the row
# recovers the whole band; the null arm certifies nothing at all.
CONTROL_GAIN = 0
PLANEK_GAIN = 8
#: the same probe with a standing field under the sweep (re-measured
#: 2026-09-07, when the field became the point the sweep starts from
#: instead of a reason to skip it).  It is EQUAL to `PLANEK_GAIN`, so
#: the two arms no longer separate on certificate count and the shifts
#: below are what this test actually holds.
PLANEK_GAIN_WITH_FIELD = 8
#: per window, the scalar the sweep chose ON TOP of the standing field
#: (measured 2026-09-07).  A window at 0.0 is the field confirmed, not
#: the field obeyed: the sweep ran and stayed.  Windows 1 and 3 are the
#: BAND pair — the two whose tiles the fixture displaced — and they do
#: not agree: 3's field carries the whole 1.75 dots and is confirmed,
#: 1's is moved three quarters of a dot the other way.
#:
#: OWED, 2026-09-08: `plane_k.LOSS_TOLERANCE` landed after these were
#: read and can only move a shift TOWARD zero — a candidate that beat
#: the field by less than 1e-6 of log loss now loses to it.  Window 1's
#: -0.75 is the one to watch: on the synthetic stimulus in
#: `test_h3_plugins_planek` a correct field's best rival wins by 6.3e-12
#: and a field 0.75 dots short loses by 3.8e-2, so a real 0.75 would
#: survive comfortably and a numerical one would not.  Which of the two
#: this is comes off the lead's oracle pass, not off inspection.
MEASURED_SHIFTS_DOTS = (0.5, -0.75, 0.5, 0.0)
NULL_GAIN = 0


@pytest.fixture(scope="module")
def emitted_page(sim_color: _h3_sims.SimCapture):
    _h3_support.skip_unless_oracle_sweeps(
        "the plane-isolation existence proof")
    assert sim_color.emit_dir is not None
    return Path(sim_color.emit_dir) / "page000_gt.npy"


def test_the_fixture_aims_at_cell_centres_not_corners():
    """THE VALUE GUARD, the twin of `test_h3_uplift_existence`'s.

    `test_h3_hygiene`'s pose gate bans the hand-built FORM this fixture
    once carried; this asks the question the gate cannot — whether the
    composed pose lands on the ink `render` actually laid down.  It
    matters more here than anywhere: half a cell is 1.5 printed dots at
    this geometry, the SAME SIZE as the plane displacement under test,
    so a fixture that missed by one would measure it as the other.

    No sim needed — the fixture's geometry against its own raster — so
    it runs in the fast lane beside the uplift twin.
    """
    row, _geometry = fixture.format_row_and_geometry()
    channel = fixture.PlaneChannel()
    span = (channel.tiles_side * TILE_CELLS) // channel.windows_side
    windows = fixture.region_windows(row, channel)
    assert len(windows) == channel.windows_side ** 2
    for window in windows:
        wy, wx = divmod(int(window.patch_ordinal), channel.windows_side)
        # `render` lays window (wy, wx)'s first cell as a PPC-sized block
        # starting here, so the cell's CENTRE is half a cell further on.
        expected = (fixture.MARGIN_PX + (wy * span + 0.5) * fixture.PPC,
                    fixture.MARGIN_PX + (wx * span + 0.5) * fixture.PPC)
        first = window.scan_points_yx[0]
        assert (float(first[0]), float(first[1])) == expected, (
            "the fixture is aiming at a cell CORNER: half a cell here is "
            "1.5 printed dots, which is the displacement this fixture "
            "exists to measure")


@pytest.fixture(scope="module")
def yellow_report(emitted_page):
    return probe.probe(emitted_page, fixture.PlaneChannel(plane=Y_PLANE))


def test_the_channel_kills_the_target_plane_on_the_band_and_nowhere_else(
        yellow_report):
    _h3_support.assert_measured("ordinary frontier",
                                len(yellow_report["frontier"]),
                                ORDINARY_FRONTIER)
    _h3_support.assert_measured("target plane certified off the band",
                                yellow_report["clean_certified"],
                                CLEAN_TARGET_CERTIFIED)
    _h3_support.assert_measured("target plane certified on the band",
                                yellow_report["band_certified"],
                                BAND_TARGET_CERTIFIED)
    _h3_support.assert_measured("target-plane residue",
                                len(yellow_report["targets"]), TARGET_RESIDUE)


def test_the_row_certifies_tiles_the_arm_off_control_cannot(yellow_report):
    _h3_support.assert_measured("arm-off control gain",
                                len(yellow_report["control"]), CONTROL_GAIN)
    _h3_support.assert_measured("planek gain", len(yellow_report["gained"]),
                                PLANEK_GAIN)
    assert len(yellow_report["gained"]) > len(yellow_report["control"])
    assert set(yellow_report["gained"]).isdisjoint(
        set(yellow_report["frontier"])), (
        "monotone by construction: a certified (address, stream) is never "
        "offered to this row")


def test_well_calibrated_evidence_at_the_wrong_address_certifies_nothing(
        yellow_report):
    _h3_support.assert_measured("null arm gain", len(yellow_report["null"]),
                                NULL_GAIN)


def test_every_certificate_matches_the_emitted_field(yellow_report):
    assert yellow_report["wrong"] == 0, (
        f"{yellow_report['wrong']} certified component bits disagree with "
        f"the emitted page — zero-wrong is the only bar this row has")


def test_the_row_emits_no_standing_evidence(yellow_report):
    """TRANSIENCE.  Every fit — the mixing model, the sampling offset, the
    PAVA map, the context correction — reaches the decoder input and is
    then dropped, so no standing cell can carry it and the ordinary
    colour head is untouched whatever this row decides."""
    kinds = {type(fact).__name__ for fact in yellow_report["gained"].values()}
    assert kinds <= {"Certificate"}
    assert probe.plane_k.PLANEK_DESCRIPTOR.produces == (AttemptFact,
                                                        Certificate)


def test_the_standing_field_is_where_the_search_starts(emitted_page):
    """The declared order, observed, and INVERTED at W3.

    Until 2026-09-07 a window the standing fit covered took that answer
    whole and did not search at all; the pin here asserted a zero shift
    on the two band windows.  The field is now the point the sweep is
    CENTRED on: every window searches, and what the source records is
    what the search was measured from — `field+search` where the page
    had solved this plane somewhere in the window, `search` where the
    field read zero across the whole of it.

    ALL FOUR windows report `field+search` on this fixture, not just
    the two over the band.  A window is 2x2 tiles and the fixture's band
    is one tile column, so every window here overlaps it, and the field
    is evaluated per cell by bilinear interpolation over the tile grid
    — a window next to a solved tile reads a small non-zero delta, which
    is the smoother doing what it is for.  Under the retired rule none
    of these four shifts would have been measured at all.

    THE TWO BAND WINDOWS DISAGREE, and the disagreement is the fixture's
    own content rather than a wrinkle in it.  Both 1 and 3 stand over
    tiles the field solved at the full 1.75 dots; 3 is confirmed at zero
    and 1 is moved -0.75.  The windows are not interchangeable — each
    scores on its own held-out labels over its own 2x2 of tiles, half of
    which lie off the band — so a shift here is a statement about one
    window's evidence and not about the field's tile values.  See the
    note on `MEASURED_SHIFTS_DOTS`: whether 1's -0.75 is evidence or
    arithmetic is exactly what the 2026-09-08 tolerance ruling decides,
    and it is owed a re-measurement on this fixture.
    """
    channel = fixture.PlaneChannel(plane=Y_PLANE)
    report = probe.probe(emitted_page, channel, with_field=True)
    sources = {ordinal: (source, shift)
               for ordinal, source, shift in report["offset_sources"]}
    assert set(sources) == {0, 1, 2, 3}
    for ordinal, (source, shift) in sources.items():
        assert source == plane_k.SOURCE_FIELD_SEARCH, (ordinal, shift)
    _h3_support.assert_measured(
          "planek sweep around a standing field",
          tuple(sources[ordinal][1] for ordinal in sorted(sources)),
          MEASURED_SHIFTS_DOTS)
    _h3_support.assert_measured("planek gain under a standing field",
                                len(report["gained"]), PLANEK_GAIN_WITH_FIELD)
    assert report["wrong"] == 0 and not report["null"]


def _seam_store(row, geometry, windows, places, planes, frontier,
                target: tuple[int, int]) -> SimpleNamespace:
    """A read-only store carrying exactly what the row's hooks consult.

    Enough of one that `color_region.region_window` runs for real: the
    row's own geometry, not a stand-in for it.
    """
    placements = {place.window_id: place for place in places}
    covers = tuple(("cap", 0, 0, window.patch_ordinal)
                   for window in windows)
    neighbours = tuple(
        (0, ty, tx, "cap", 0)
        for ty in range(target[0] - 1, target[0] + 2)
        for tx in range(target[1] - 1, target[1] + 2))
    ordinal_wid = {window.patch_ordinal: window.window_id
                   for window in windows}
    return SimpleNamespace(
        row=row, geometry=geometry,
        cover_lanes=lambda page, ty, tx, ppc: (("cap", 0),),
        tile_cover=lambda key: ((), covers),
        evidence_reach=lambda wid: None,
        color_row_cover_tiles=lambda key: neighbours,
        window_by_ordinal=lambda cap, level, ordinal: ordinal_wid[ordinal],
        window=lambda wid: SimpleNamespace(region_index=0),
        placement=lambda wid: placements[wid],
        level=lambda cap, level: SimpleNamespace(scale=Fraction(1)),
        rgb_planes=lambda lane: planes,
        page_plane_fields=lambda page: (None, None, None),
        certificates=lambda: dict(frontier),
        has_certificate=lambda key: key in frontier,
        union_rung_ordinal=lambda ppc: 0)


def test_prepare_builds_a_plan_whose_job_certifies_through_the_row_seam(
        emitted_page):
    """The scheduler seam, exercised deliberately.

    The clean sims never fire this row — its price puts it last and by
    then the page is done — so the path it will actually run through on
    a real sheet has to be reached on purpose: subject in, `prepare` out,
    job run, certificate minted.
    """
    channel = fixture.PlaneChannel(plane=Y_PLANE)
    row, geometry = fixture.format_row_and_geometry()
    bits = fixture.page_bits(emitted_page, row)
    image = fixture.render(bits, channel)
    windows = fixture.region_windows(row, channel)
    places = fixture.placements(channel)
    streams = tuple(stream.stream_id for stream in row.streams)
    every = tuple((ty, tx, streams) for ty in range(channel.tiles_side)
                  for tx in range(channel.tiles_side))
    stream_id = probe.stream_of_plane(row, Y_PLANE)
    with tempfile.TemporaryDirectory() as tmp:
        planes = fixture.plane_rasters(image, Path(tmp))
        frontier, _v, _i, _s = probe.ordinary.run_tier(
            row, geometry, windows, planes, {}, every,
            probe.ordinary.ARM_OFF, None)
        target = fixture.band_tiles(channel)[0]
        store = _seam_store(row, geometry, windows, places, planes,
                            dict(frontier), target)
        subject = (0, target[0], target[1], stream_id, Fraction(1))
        assert plane_k._planek_eligible(store, subject)
        assert not plane_k._planek_retire(store, subject)
        job = plane_k.prepare_planek(store, subject, plane_k.STAGE_PLANEK)
        assert job is not None
        result = job()
    minted = {(fact.page, fact.ty, fact.tx, fact.stream_id)
              for fact in result.facts if hasattr(fact, "user_bits")}
    assert minted == {(0, target[0], target[1], stream_id)}
    assert minted.isdisjoint(set(frontier))
    assert result.cpu_s > 0.0, (
        "per-tool accounting: this row owns a three-channel re-read and "
        "an offset search no other row's meter covers")
    kinds = {type(fact).__name__ for fact in result.facts}
    assert kinds <= {"AttemptFact", "Certificate"}


def test_the_row_never_fires_on_a_clean_colour_sim(decode_color_w8):
    """THE NULL ARM AT RUN SCALE.  On a page whose residue the ordinary
    rows resolve, this one is priced past the end of the drain and does
    no work at all — so the clean sims decode byte-identically with it
    present, which is what the cross-tree null measured."""
    fires = sum(1 for event in decode_color_w8.events
                if isinstance(event, data.JobDone)
                and event.plugin == plane_k.PLUGIN)
    _h3_support.assert_measured("planek fires on the clean colour sim",
                                fires, 0)


@pytest.mark.parametrize("plane", (0, 1))
def test_the_mechanism_is_plane_general(emitted_page, plane):
    """Cyan off red and magenta off green, same code path, same result:
    nothing in the row privileges the plane the experiment measured."""
    report = probe.probe(emitted_page, fixture.PlaneChannel(plane=plane))
    _h3_support.assert_measured(f"plane {plane} residue",
                                len(report["targets"]), TARGET_RESIDUE)
    _h3_support.assert_measured(f"plane {plane} arm-off control gain",
                                len(report["control"]), CONTROL_GAIN)
    _h3_support.assert_measured(f"plane {plane} planek gain",
                                len(report["gained"]), PLANEK_GAIN)
    assert report["wrong"] == 0 and not report["null"]
