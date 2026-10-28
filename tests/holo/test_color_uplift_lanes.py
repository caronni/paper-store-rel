"""PK4.3 supplemental lanes: the scheduled — not gated — arm form.

RECEIVE-DESIGN §6.2a's law, as pins:

* an arm that cannot prove universal non-regression is SCHEDULED, so a
  COLOR plan carries a supplemental tail after the standard l/m/r
  sequence and a K plan carries none;
* the override rides the lane IDENTITY — derived, never persisted as a
  new field, never ambient — and an ordinary lane cannot carry one;
* THE SAFETY ARGUMENT IS §6.3's per-address retirement law, exercised at
  the u-lane boundary: a supplemental lane cannot attempt a certified
  address, so its certificate delta is non-negative by construction;
* ``--force-null`` means the pre-campaign receiver EXACTLY, so a u-lane
  does not attempt at all under it — not even with its arm off;
* each override bypasses exactly ONE arm's applicability decision (A3's
  two parked dispersion floors; A4b's park flag and region gate) and
  leaves every per-unit pre-gate, every other arm, and the standard
  ladder untouched.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

import _color_stack_fixtures as stack_fixtures
import test_color_conditioning as cmy8_fixtures
import test_color_locality as locality_fixtures
import test_receive_color_refine as refine_fixtures
from holo.format.profiles import Family
from holo.receive import (
    color_conditioning as cc,
    color_context,
    color_field,
    color_payload,
    color_stack,
    production_color,
    production_payload,
)
from holo.receive.cascade import lane_kind, scale_plan
from holo.receive.color_payload import collect_color_evidence
from holo.receive.color_stack import (
    UPLIFT_ARM_A3,
    UPLIFT_ARM_A4B,
    UPLIFT_ARM_OFF,
)
from holo.receive.evidence_context import EvidenceContext
from holo.receive.lane_uplift import (
    UPLIFT_ARMS,
    parse_uplift_lane_id,
    uplift_lane_id,
)
from holo.receive.runtime import _plan_bound
from holo.receive.types import (
    AddressArtifact,
    AddressProduct,
    LaneSpec,
    RefineAddressPlan,
    SurveyArtifact,
    SurveyProduct,
)


COLOR_ROW = "c3-cmy8-p120-v0@2240x1536"
K_CODEC = "k-v1"


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------


def test_color_plan_appends_two_supplemental_lanes_at_the_finest_rung(
) -> None:
    """``[L…, M…, R…, U(Ln,off), U(Ln,a3), U(Ln,a4b), U(Ln,field)]`` —
    one per registered override, the BASELINE one first (PK5) and the
    field arm LAST (PLANE-FIELDS W3: it consumes what the others mint)."""
    plan = scale_plan(4800.0, 3, codec_family=Family.CMY8, n_streams=3)
    ladder = [row for row in plan
              if row.mopup_of is None and row.refine_of is None
              and row.uplift_of is None]
    uplift = [row for row in plan if row.uplift_of is not None]
    assert len(plan) == 3 * len(ladder) + len(UPLIFT_ARMS)
    # The tail, and only the tail.
    assert [row.lane_id for row in plan[-len(UPLIFT_ARMS):]] == [
        row.lane_id for row in uplift]
    finest = ladder[-1]
    assert [row.arm_override for row in uplift] == list(UPLIFT_ARMS)
    for row in uplift:
        # Bound to the finest rung: same base, same exact ratios, same
        # raster derivation — a u-lane derives no new level.
        assert row.uplift_of == finest.lane_id == row.base_lane_id
        assert (row.target_ppc_num, row.target_ppc_den) == (
            finest.target_ppc_num, finest.target_ppc_den)
        assert (row.native_per_view_num, row.native_per_view_den) == (
            finest.native_per_view_num, finest.native_per_view_den)
        # Own evidence namespace (only certificates cross lanes).
        assert row.evidence_lane_id == row.lane_id
        assert lane_kind(row) == f"uplift:{row.arm_override}"
    # One ordered parent chain, still.
    assert [row.parent_lane_id for row in plan[1:]] == [
        row.lane_id for row in plan[:-1]]


def test_k_plan_gains_no_supplemental_lane() -> None:
    """Supplemental lanes are COLOR-ONLY: every override is a colour
    configuration, including the one that turns the arms OFF."""
    plan = scale_plan(4800.0, 3, codec_family=Family.K, n_streams=1)
    assert not [row for row in plan if row.uplift_of is not None]
    assert len(plan) % 3 == 0
    # And the default is K, so a caller without a spec cannot mint them.
    assert scale_plan(4800.0, 3) == plan
    # If one ever reached the K payload leaf it refuses loudly rather
    # than decoding K evidence under a color-stack arm override.
    lane = LaneSpec(uplift_lane_id("l00-2ppc-600dpi", "a3"), 2, 1, 1, 1)

    class _Context:
        pass

    context = _Context()
    context.lane = lane  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="schedules no supplemental lane"):
        production_payload.ProductionPayload().process(
            context, None, None)  # type: ignore[arg-type]


def test_lane_identity_carries_the_override() -> None:
    """The id IS the declaration: derived both ways, exactly."""
    # The lane vocabulary and the ladder's reading of it must agree —
    # `lane_uplift` owns the ids; the module that IMPLEMENTS an arm owns
    # its name (`color_stack` for the three campaign arms, `color_field`
    # for the PLANE-FIELDS W3 registration arm).
    assert set(UPLIFT_ARMS) == {
        color_stack.UPLIFT_ARM_OFF, color_stack.UPLIFT_ARM_A3,
        color_stack.UPLIFT_ARM_A4B, color_field.UPLIFT_ARM_FIELD}
    # PK5: ORDER is part of the law, not presentation — the baseline lane
    # completes the OLD configuration's reachable set before either forced
    # arm reads the residue.
    assert UPLIFT_ARMS[0] == color_stack.UPLIFT_ARM_OFF
    for arm in UPLIFT_ARMS:
        lane_id = uplift_lane_id("l04-24ppc-4800dpi", arm)
        assert lane_id == f"u04-{arm}-24ppc-4800dpi"
        assert parse_uplift_lane_id(lane_id) == ("l04-24ppc-4800dpi", arm)
        lane = LaneSpec(lane_id, 24, 1, 1, 1)
        assert lane.arm_override == arm
        assert lane.uplift_of == lane.base_lane_id == "l04-24ppc-4800dpi"
    # Fractional-ppc labels survive the round trip.
    assert parse_uplift_lane_id(
        uplift_lane_id("l01-3-2ppc-900dpi", "a3")) == (
            "l01-3-2ppc-900dpi", "a3")
    # Nothing else is a u-lane, and no ordinary lane carries an override.
    for other in ("l00-2ppc-600dpi", "m00-2ppc-600dpi", "r00-2ppc-600dpi",
                  "u", "u0-a3-2ppc", "uplift", "u00-a9-2ppc-600dpi",
                  "u00-a3-"):
        assert parse_uplift_lane_id(other) is None
        assert LaneSpec(other, 2, 1, 1, 1).arm_override is None
    with pytest.raises(ValueError, match="unregistered uplift arm"):
        uplift_lane_id("l00-2ppc-600dpi", "a9")
    # A level is exactly one of the four classes.
    with pytest.raises(ValueError, match="neither a mop-up nor a refine"):
        LaneSpec(uplift_lane_id("l00-2ppc-600dpi", "a3"), 2, 1, 1, 1,
                 refine_of="l00-2ppc-600dpi")


def test_supplemental_lanes_ride_refine_and_run_last() -> None:
    """The plan's last family: after every lane that could shrink the
    residue, and behind the flag that means "the whole plan"."""
    plan = scale_plan(4800.0, 3, codec_family=Family.CMY8, n_streams=3)
    n_uplift = len(UPLIFT_ARMS)
    assert _plan_bound(plan, run_mopup=False, run_refine=True) == len(plan)
    # Neither the default nor --mopup reaches them.
    for bound in (
        _plan_bound(plan, run_mopup=False, run_refine=False),
        _plan_bound(plan, run_mopup=True, run_refine=False),
    ):
        assert bound <= len(plan) - n_uplift
        assert all(row.uplift_of is None for row in plan[:bound])


# ---------------------------------------------------------------------------
# the u-lane leaf
# ---------------------------------------------------------------------------


def _uplift_products(raster, lane_id: str, plan: RefineAddressPlan):
    survey = SurveyProduct(
        SurveyArtifact(f"{raster.source.sha256}/{lane_id}/survey", ()), ())
    address = AddressProduct(
        AddressArtifact(
            f"{raster.source.sha256}/{lane_id}/address",
            survey.artifact.survey_id, ()),
        (), transient=plan)
    return survey, address


def _run_uplift(spec, raster, plan, region_record, poses, arm, events,
                base_lane_id, processor=None):
    """``processor`` lets a caller hand the lane a configured dial.

    ``None`` is the standing ``ProductionColorPayload()`` every existing
    caller gets, unchanged; a caller that needs a non-default
    ``plane_fields`` dial (the probe-density pose regression,
    ``test_plane_field_pose_regression``) passes its own.
    """
    lane = LaneSpec(
        uplift_lane_id(base_lane_id, arm),
        2, 1, 1, 1)
    context = refine_fixtures._lane_context(
        spec, raster, events,
        EvidenceContext(
            certificates=plan.certificates,
            regions=(region_record,),
            label_poses=poses),
        lane=lane)
    survey, address = _uplift_products(raster, lane.lane_id, plan)
    if processor is None:
        processor = production_color.ProductionColorPayload()
    return context, processor.process(context, survey, address)


def _cmy7_uplift_fixture():
    """One committed window, 4 of its 6 tiles already certified."""
    spec, raster, address, _source, certs = (
        refine_fixtures._single_window_fixture())
    events: list = []
    _context, region_record, address_product, _output = (
        refine_fixtures._base_barrier(spec, raster, address, certs, events))
    plan = RefineAddressPlan(
        base_lane_id=refine_fixtures.LANE,
        poses=address_product.poses,
        regions=(region_record,),
        certificates=certs,
    )
    return spec, raster, plan, region_record, address_product.poses


def test_a_supplemental_lane_cannot_attempt_a_certified_address() -> None:
    """THE SUPPRESSION PIN — §6.3's retirement law at the u-lane boundary.

    This is the whole reason a u-lane needs no adoption gate.  The store
    is restored from the accumulated frontier before the leaf runs, so
    ``unresolved_streams`` never offers a certified (address, stream)
    and the lane's reachable set is exactly the uncertified residue.
    Monotonicity is therefore structural — and here it is measured.
    """
    spec, raster, plan, region_record, poses = _cmy7_uplift_fixture()
    certified = {
        (row.page, *row.tile_yx, row.stream_id) for row in plan.certificates}
    assert certified, "the fixture must certify something to suppress"

    events: list = []
    _context, output = _run_uplift(
        spec, raster, plan, region_record, poses, "a3", events,
        refine_fixtures.LANE)
    product = output.product
    assert product is not None

    attempted = {
        (row.page, *row.tile_yx, row.stream_id) for row in product.attempts}
    assert attempted, "the residue must actually be attempted"
    # Not one attempt, at any stage, on a certified stream.
    assert not attempted & certified
    # And therefore not one minted certificate on one either: every
    # certificate a u-lane mints is an ADD.
    minted = {
        (row.page, *row.tile_yx, row.stream_id)
        for row in product.certificates}
    assert not minted & certified
    # A u-lane refines nothing, so it mints no replacement address.
    assert output.replacement_address is None
    # The lane's own evidence namespace, and the arm on the record.
    lane_id = uplift_lane_id(refine_fixtures.LANE, "a3")
    assert all(row.lane_id == lane_id for row in product.blocks)
    names = [name for name, _details in events]
    plan_details = refine_fixtures._detail_map(
        events[names.index("payload.plan")][1])
    assert plan_details["color.uplift_arm"] == "a3"
    assert plan_details["color.uplift_of"] == refine_fixtures.LANE
    assert "pose_refine.window_progress" not in names
    assert "address.final" not in names


def test_force_null_skips_the_supplemental_lane_entirely(monkeypatch) -> None:
    """force-null ≡ the pre-campaign receiver, EXACTLY.

    Running a u-lane with its arm off would not be a null — it would be
    an extra committed-pose decode pass the pre-campaign receiver never
    made, with its own attempts, blocks and cost.  So the lane does not
    attempt at all, and never touches a pixel.
    """
    spec, raster, plan, region_record, poses = _cmy7_uplift_fixture()
    sealed = refine_fixtures._NoPixelRaster(
        raster.source, tuple(raster.shape), raster.dpi)
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    events: list = []
    _context, output = _run_uplift(
        spec, sealed, plan, region_record, poses, "a3", events,
        refine_fixtures.LANE)
    product = output.product
    assert product is not None
    assert not product.blocks and not product.attempts
    assert not product.certificates
    assert output.replacement_address is None
    assert events == []


def test_a_fully_certified_page_never_reads_pixels() -> None:
    """The R leaf's pixel-free pre-gates, inherited verbatim."""
    spec, raster, address, _source, certs = (
        refine_fixtures._single_window_fixture())
    symbols = refine_fixtures._compose_field(spec, (2, 3), 0xC0161)[1]
    everything = refine_fixtures._certificates(
        spec, symbols,
        tuple((ty, tx) for ty in range(2) for tx in range(3)))
    events: list = []
    _context, region_record, address_product, _output = (
        refine_fixtures._base_barrier(spec, raster, address, certs, events))
    plan = RefineAddressPlan(
        base_lane_id=refine_fixtures.LANE,
        poses=address_product.poses,
        regions=(region_record,),
        certificates=everything,
    )
    sealed = refine_fixtures._NoPixelRaster(
        raster.source, tuple(raster.shape), raster.dpi)
    u_events: list = []
    _context, output = _run_uplift(
        spec, sealed, plan, region_record, address_product.poses,
        "a3", u_events, refine_fixtures.LANE)
    product = output.product
    assert product is not None
    assert not product.blocks and not product.attempts
    assert u_events == []


def _zero_frontier_plan():
    """Committed poses and a region, but NOT ONE prior certificate.

    The B6-control shape: a page the ordinary ladder addressed and then
    failed to certify anything on.  Everything the leaf places against is
    present; only the frontier is empty.
    """
    spec, raster, address, _source, certs = (
        refine_fixtures._single_window_fixture())
    events: list = []
    _context, region_record, address_product, _output = (
        refine_fixtures._base_barrier(spec, raster, address, certs, events))
    plan = RefineAddressPlan(
        base_lane_id=refine_fixtures.LANE,
        poses=address_product.poses,
        regions=(region_record,),
        certificates=(),
    )
    assert plan.poses and plan.regions and not plan.certificates
    return spec, raster, plan, region_record, address_product.poses


@pytest.mark.parametrize("arm", (UPLIFT_ARM_OFF, UPLIFT_ARM_A3))
def test_a_zero_frontier_capture_still_runs_off_and_a3(arm: str) -> None:
    """THE ZERO-FRONTIER PIN — §6.2a v0.54's arm-split pre-gate.

    U(off) and U(a3) fit from committed FURNITURE and read no
    certificate, so an empty frontier does not make them vacuous — it is
    exactly the stranding case U(off) is scheduled for.  Until v4 the
    leaf inherited the R level's "no certificates => stop" gate verbatim
    and refused both arms, pixel-free and without a word in the event
    stream, on precisely the hardest pages.  The claim here is only that
    the lane REACHES its evidence collection; what it then certifies is
    the channel's business, not the gate's.
    """
    spec, raster, plan, region_record, poses = _zero_frontier_plan()
    events: list = []
    _context, output = _run_uplift(
        spec, raster, plan, region_record, poses, arm, events,
        refine_fixtures.LANE)
    product = output.product
    assert product is not None
    assert product.blocks and product.attempts
    names = [name for name, _details in events]
    assert "payload.plan" in names
    plan_details = refine_fixtures._detail_map(
        events[names.index("payload.plan")][1])
    assert plan_details["color.uplift_arm"] == arm
    assert plan_details["color.prior_certificates"] == 0
    # Every certificate a u-lane mints is an ADD, and with nothing
    # certified before it, all of them are.
    assert not {row.certificate_id for row in product.certificates} & {
        row.certificate_id for row in plan.certificates}


def test_a_zero_frontier_capture_still_refuses_a4b() -> None:
    """The other half of the split: A4b alone NEEDS a frontier.

    Its whole arm is conditioning a plane's cells on the states its
    certified SIBLING planes fix, so with no certificate there is nothing
    to condition on and the lane is a guaranteed zero.  It refuses the
    way it always did — pixel-free, no events.  (The leaf gate is
    codec-blind; a cmy7 PLAN never schedules this lane at all, per the
    ``codingaware`` filter.)
    """
    spec, raster, plan, region_record, poses = _zero_frontier_plan()
    sealed = refine_fixtures._NoPixelRaster(
        raster.source, tuple(raster.shape), raster.dpi)
    events: list = []
    _context, output = _run_uplift(
        spec, sealed, plan, region_record, poses, UPLIFT_ARM_A4B, events,
        refine_fixtures.LANE)
    product = output.product
    assert product is not None
    assert not product.blocks and not product.attempts
    assert not product.certificates
    assert output.replacement_address is None
    assert events == []


# ---------------------------------------------------------------------------
# the two overrides
# ---------------------------------------------------------------------------


def _region_summary(arm: str | None, per_stream=None, row=COLOR_ROW):
    spec, raster, address, source, certs, _field = cmy8_fixtures._fixture(
        per_stream, row)
    evidence = collect_color_evidence(
        raster, source, address, spec,
        certificates=certs, arm_override=arm)
    assert len(evidence.regions) == 1
    return evidence.regions[0]


def test_uplift_off_is_the_pre_campaign_ladder_over_the_residue() -> None:
    """PK5: the supplemental BASELINE lane.

    The third override does not force an arm — it removes every one of
    them, so the lane decodes the residue through the evidence path the
    receiver had BEFORE the campaign.  That is what makes a ladder
    CONFIGURATION change safe: adopting an arm re-times the cascade and
    can strand a tile the old path certified, and the old path's own tail
    is schedulable under the same per-address retirement law.

    The pin is that the lane's evidence is the force-null path's, value
    for value, while the standard ladder on the SAME fixture is not — a
    comparison that would be vacuous unless an arm actually fires, so the
    channel is PK5's bleeding one, where A5 adopts.
    """
    fixture = stack_fixtures.build_context_fixture(
        3.0, 0.01, row_id="c3-cmy8-p120-v0@2240x1536")

    def run(arm, force_null=False):
        previous = os.environ.get(color_stack.FORCE_NULL_ENV)
        if force_null:
            os.environ[color_stack.FORCE_NULL_ENV] = "1"
        try:
            product = collect_color_evidence(
                fixture.raster, fixture.source, fixture.address,
                fixture.spec, arm_override=arm)
        finally:
            if previous is None:
                os.environ.pop(color_stack.FORCE_NULL_ENV, None)
            else:
                os.environ[color_stack.FORCE_NULL_ENV] = previous
        return product, {int(window.patch_id): np.asarray(
            window.evidence_values) for window in product.windows}

    standard, standard_cells = run(None)
    forced_off, off_cells = run("off")
    _null, null_cells = run(None, force_null=True)

    # The premise: the standard ladder is NOT the null on this channel.
    assert standard.regions[0].context.adopted
    assert all(not np.array_equal(values, null_cells[patch_id])
               for patch_id, values in standard_cells.items())
    # The ruling: the u-off lane IS the null, cell for cell.
    assert off_cells.keys() == null_cells.keys()
    for patch_id, values in off_cells.items():
        assert np.array_equal(values, null_cells[patch_id]), patch_id
    # ...and it says so: no arm reports having run, and the region names
    # its lane's arm, so a summary can never be read as a standard one.
    region = forced_off.regions[0]
    assert region.uplift_arm == "off"
    assert region.context == color_context.ContextSummary()
    assert region.conditioning == cc.ConditioningSummary()
    assert region.window_photometry.accepted == 0
    assert region.window_photometry.refused == 0
    assert standard.regions[0].uplift_arm == ""


def test_the_standard_ladder_never_calls_either_arms_fitter() -> None:
    """THE OVERRIDE-ONLY PIN (PK-CLEAN), structural and spied.

    A3 and A4b are reachable ONLY through a supplemental lane's
    ``arm_override``: there is no constant, no flag and no environment
    variable that could engage them from an ordinary, mop-up or
    refinement level.  The pin is a counter on both fitters, run on the
    fixture where BOTH arms do fire under their own overrides — so it
    cannot pass because the fixture is inert.
    """
    per_stream = {"C": cmy8_fixtures._C_TILES, "M": cmy8_fixtures._M_TILES}
    calls: list[str] = []
    photometry = color_stack.fit_window_photometry
    conditioning = color_stack.fit_conditioned_marginals

    def spy_photometry(*args, **kwargs):
        calls.append("a3")
        return photometry(*args, **kwargs)

    def spy_conditioning(*args, **kwargs):
        calls.append("a4b")
        return conditioning(*args, **kwargs)

    color_stack.fit_window_photometry = spy_photometry
    color_stack.fit_conditioned_marginals = spy_conditioning
    try:
        _region_summary(None, per_stream)
        assert calls == [], calls
        _region_summary("off", per_stream)
        assert calls == [], calls
        _region_summary("a3", per_stream)
        assert calls == ["a3"], calls
        calls.clear()
        _region_summary("a4b", per_stream)
        assert calls == ["a4b"], calls
    finally:
        color_stack.fit_window_photometry = photometry
        color_stack.fit_conditioned_marginals = conditioning


def test_uplift_a3_is_the_only_way_the_arm_runs_at_all() -> None:
    """A3's summary is the DEFAULT instance off its own lane.

    Its two region applicability floors are RETIRED (measured
    non-separating, MEASUREMENTS §6.3/§7.4/§12), so there is nothing left
    for a u-lane to bypass — the lane's job is now to make the arm
    reachable, not to unpark it.  The EFFECTIVE swept constant is still
    published per region, so the pin reads what the arm fitted with
    rather than trusting the token.
    """
    from holo.receive import color_locality

    standard = _region_summary(None).window_photometry
    forced = _region_summary("a3").window_photometry
    assert standard == color_locality.WindowPhotometrySummary()
    assert standard.accepted == standard.refused == 0
    assert forced.accepted + forced.refused > 0
    assert forced.prior_labels == color_locality.WINDOW_PHOT_PRIOR_LABELS
    assert forced.reason in (
        color_locality.REASON_ADOPTED,
        color_locality.REASON_REGION_GATE_FAILED,
        color_locality.REASON_NO_WINDOW_MAPS)
    # The arm is published per region, so a summary cannot be mistaken
    # for a standard-ladder one.
    assert _region_summary("a3").uplift_arm == "a3"
    assert _region_summary(None).uplift_arm == ""


def test_uplift_a3_runs_the_arm_the_campaign_measured() -> None:
    """The lane on the channel PK4.1's retired floor used to refuse.

    ``UNIFORM_GAIN`` is the page-wide gain: windows DO earn maps and
    their fitted gains barely disagree, which is exactly the region the
    dispersion floor was invented to refuse.  With the floor retired the
    only things left are the per-window pre-gate and the standing
    three-way region comparison — and the lane runs both.
    """
    fixture = locality_fixtures.build_locality_fixture(
        locality_fixtures.LOCALITY_BLUR,
        locality_fixtures.UNIFORM_NOISE,
        locality_fixtures.NO_GAIN_GRADIENT,
        locality_fixtures.UNIFORM_GAIN,
        row_id=locality_fixtures.UNIFORM_ROW)

    def region(arm):
        rows: list = []
        collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec,
            region_progress=rows.append, arm_override=arm)
        return rows[0].window_photometry

    from holo.receive import color_locality

    standard = region(None)
    assert standard == color_locality.WindowPhotometrySummary()

    forced = region("a3")
    assert forced.accepted >= 2
    assert forced.reason in (
        color_locality.REASON_ADOPTED,
        color_locality.REASON_REGION_GATE_FAILED)


def test_uplift_a4b_is_the_only_way_the_arm_runs_at_all() -> None:
    """A4b off its lane is ABSENT: not one diagnostic key.

    On its own lane the arm runs and its REGION comparison is measured,
    published and not consulted — the verdict is ``region_gate_forced``,
    which is the measured answer to §9.4/§9.8 (that gate, not the
    material, is what made the arm unreachable rather than unhelpful).
    """
    per_stream = {"C": cmy8_fixtures._C_TILES, "M": cmy8_fixtures._M_TILES}
    standard = _region_summary(None, per_stream).conditioning
    assert standard == cc.ConditioningSummary()
    assert standard.reason == ""

    forced = _region_summary("a4b", per_stream).conditioning
    assert forced.reason == cc.CONDITIONING_REASON_REGION_FORCED
    assert forced.adopted
    # The per-STRATUM pre-gate still rules — a forced lane is not a
    # forced construction.
    assert forced.strata
    assert forced.adopted_strata >= 1
    # All three region legs are still measured, so the adoption reports
    # the numbers it did not consult instead of hiding them.
    assert forced.incumbent_nll >= 0.0 and forced.candidate_nll >= 0.0
    assert forced.word_incumbent_nll >= 0.0
    assert forced.dust_incumbent_nll >= 0.0
    # cmy7 stays a strict no-op under the same override: A4b is CMY8's
    # half of the rung, and forcing a lane cannot change whose half.
    assert _region_summary(
        "a4b", {"main": cmy8_fixtures._C_TILES},
        row=cmy8_fixtures.CMY7_ROW,
    ).conditioning == cc.ConditioningSummary()


def test_a_forced_lane_adopts_over_an_adverse_region_comparison(
    monkeypatch,
) -> None:
    """The case that made forcing necessary: a region gate that REFUSES.

    Measured (§9.4/§9.8), that refusal — on the dust leg, with total and
    word improving — is what made A4b unreachable rather than unhelpful
    on the uplift target, so its lane decodes past it.  The synthetic
    fixture's own comparison passes, which would leave the claim
    untested, so the legs are forced adverse here: the candidate is
    strictly WORSE on all three and the arm adopts anyway, with the
    numbers it did not consult on the record.
    """
    def adverse(detector, gate, head):
        return (1.0, 1.0, 1.0) if head is None else (2.0, 2.0, 2.0)

    monkeypatch.setattr(cc, "_region_losses", adverse)
    per_stream = {"C": cmy8_fixtures._C_TILES, "M": cmy8_fixtures._M_TILES}
    forced = _region_summary("a4b", per_stream).conditioning
    assert forced.reason == cc.CONDITIONING_REASON_REGION_FORCED
    assert forced.adopted
    assert (forced.candidate_nll, forced.incumbent_nll) == (2.0, 1.0)
    assert forced.dust_candidate_nll > forced.dust_incumbent_nll
    # A stratum that failed its OWN pre-gate is still absent.
    assert forced.adopted_strata >= 1


def test_forced_region_adoption_keeps_its_own_reason() -> None:
    """"adopted" must keep meaning "the region comparison said yes"."""
    assert (cc.CONDITIONING_REASON_REGION_FORCED
            != cc.CONDITIONING_REASON_ADOPTED)
    summary = cc.ConditioningSummary(
        reason=cc.CONDITIONING_REASON_REGION_FORCED, adopted=True)
    assert summary.adopted_strata == 0
    with pytest.raises(cc.ConditioningError):
        cc.ConditioningSummary(
            reason=cc.CONDITIONING_REASON_NO_STRATUM, adopted=True)


def test_the_override_is_never_ambient() -> None:
    """No environment hatch, no default: it comes from a lane or not
    at all, and an unregistered name is refused at the ladder."""
    spec, raster, address, source, certs, _field = cmy8_fixtures._fixture(
        {"C": cmy8_fixtures._C_TILES})
    with pytest.raises(ValueError, match="unregistered uplift arm"):
        collect_color_evidence(
            raster, source, address, spec,
            certificates=certs, arm_override="a9")
    # The ladder's own signature default is the standing receiver.
    import inspect

    signature = inspect.signature(color_stack.fit_region_stack)
    assert signature.parameters["arm_override"].default is None
    signature = inspect.signature(color_payload.collect_color_evidence)
    assert signature.parameters["arm_override"].default is None


def test_an_ordinary_lane_is_byte_identical_with_the_tail_scheduled(
) -> None:
    """Scheduling u-lanes changes no ordinary lane's evidence.

    The supplemental tail is appended to the PLAN; it does not unpark
    anything for the standard ladder, so a lane that ran before the
    packet must produce the same bytes after it.
    """
    per_stream = {"C": cmy8_fixtures._C_TILES, "M": cmy8_fixtures._M_TILES}
    spec, raster, address, source, certs, _field = cmy8_fixtures._fixture(
        per_stream)
    left = collect_color_evidence(
        raster, source, address, spec, certificates=certs)
    right = collect_color_evidence(
        raster, source, address, spec, certificates=certs,
        arm_override=None)
    assert len(left.windows) == len(right.windows)
    for one, two in zip(left.windows, right.windows, strict=True):
        assert np.array_equal(one.page_cells_yx, two.page_cells_yx)
        assert one.evidence_values.tobytes() == two.evidence_values.tobytes()
    assert left.regions[0].conditioning == cc.ConditioningSummary()
