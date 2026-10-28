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

from holo3 import data
from holo3.data import AttemptFact, Certificate
from holo3.lib.geometry import TILE_CELLS
from holo3.plugins import plane_k
from holo3.tests import _h3_sims, _h3_support

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
    _h3_support.assert_golden("ordinary frontier",
                              len(yellow_report["frontier"]),
                              ORDINARY_FRONTIER)
    _h3_support.assert_golden("target plane certified off the band",
                              yellow_report["clean_certified"],
                              CLEAN_TARGET_CERTIFIED)
    _h3_support.assert_golden("target plane certified on the band",
                              yellow_report["band_certified"],
                              BAND_TARGET_CERTIFIED)
    _h3_support.assert_golden("target-plane residue",
                              len(yellow_report["targets"]), TARGET_RESIDUE)


def test_the_row_certifies_tiles_the_arm_off_control_cannot(yellow_report):
    _h3_support.assert_golden("arm-off control gain",
                              len(yellow_report["control"]), CONTROL_GAIN)
    _h3_support.assert_golden("planek gain", len(yellow_report["gained"]),
                              PLANEK_GAIN)
    assert len(yellow_report["gained"]) > len(yellow_report["control"])
    assert set(yellow_report["gained"]).isdisjoint(
        set(yellow_report["frontier"])), (
        "monotone by construction: a certified (address, stream) is never "
        "offered to this row")


def test_well_calibrated_evidence_at_the_wrong_address_certifies_nothing(
        yellow_report):
    _h3_support.assert_golden("null arm gain", len(yellow_report["null"]),
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


def test_the_standing_field_is_consulted_before_the_blind_estimator(
        emitted_page):
    """The declared order, observed: where a field is published with
    support in reach the row samples where it points and does NOT search;
    where the field is silent the blind estimator covers."""
    channel = fixture.PlaneChannel(plane=Y_PLANE)
    report = probe.probe(emitted_page, channel, with_field=True)
    band_windows = {1, 3}
    sources = {ordinal: (source, shift)
               for ordinal, source, shift in report["offset_sources"]}
    assert set(sources) == {0, 1, 2, 3}
    for ordinal, (source, shift) in sources.items():
        if ordinal in band_windows:
            assert source == "field" and shift == 0.0, (
                "a window the standing fit covers takes the standing "
                "answer whole — no scalar search on top of it")
        else:
            assert source == "blind"
    _h3_support.assert_golden("planek gain under a standing field",
                              len(report["gained"]), PLANEK_GAIN)
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
        plane_field=lambda key: None,
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
            probe.ordinary.ARM_OFF)
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
    _h3_support.assert_golden("planek fires on the clean colour sim",
                              fires, 0)


@pytest.mark.parametrize("plane", (0, 1))
def test_the_mechanism_is_plane_general(emitted_page, plane):
    """Cyan off red and magenta off green, same code path, same result:
    nothing in the row privileges the plane the experiment measured."""
    report = probe.probe(emitted_page, fixture.PlaneChannel(plane=plane))
    _h3_support.assert_golden(f"plane {plane} residue",
                              len(report["targets"]), TARGET_RESIDUE)
    _h3_support.assert_golden(f"plane {plane} arm-off control gain",
                              len(report["control"]), CONTROL_GAIN)
    _h3_support.assert_golden(f"plane {plane} planek gain",
                              len(report["gained"]), PLANEK_GAIN)
    assert report["wrong"] == 0 and not report["null"]
