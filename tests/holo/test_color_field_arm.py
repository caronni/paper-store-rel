"""PLANE-FIELDS W3: ``uF``, the supplemental lane that reads the residue
through the per-plane delta field.

W2 built the field and left it behind a dial that no production decode
turns on.  W3 is how it reaches paper: not a gate, a LANE.  RECEIVE-DESIGN
§6.2a's schedule law says an arm that cannot prove universal
non-regression is scheduled after the standard ladder, where §6.3's
per-address retirement makes it monotone by construction — so the field
becomes a fourth registered arm, ``field``, and the arm IS the opt-in.

Four claims, in the order they matter.

1. **It fires on the residue and recovers the plane** — the W2 warped
   fixture (an M-plane x-sinusoid outside ``PlaneResidual``'s {1, y}
   basis) decoded through the whole plan: the ordinary lanes lose M
   certificates, the ``uF`` lane at the end of the tail wins them back,
   and the certificates it mints join to ITS attempts by lane id.
2. **It cannot lose** — the unwarped twin gains nothing and loses
   nothing, because a page whose every committed span is certified
   pre-gates the lane free before it touches a pixel.
3. **It is a REGISTRATION arm, not a stack arm** — the evidence ladder
   does not recognize the name, so at the collection seam
   ``arm_override="field"`` is the standard ladder cell for cell; the
   only thing the arm changes is which dial its own lane collects under.
4. **The plan says so** — every colour coding schedules it (planes, not
   streams: cmy7 rides one stream and three planes), K schedules none,
   and it runs LAST because it consumes the certificates the earlier
   lanes and arms mint.
"""
from __future__ import annotations

import hashlib
import os
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

import _color_stack_fixtures as stack_fixtures
import test_color_field as w2
import test_color_uplift_lanes as uplift_fixtures
import test_receive_color_refine as refine_fixtures
from holo.format.profiles import Family
from holo.gen.emit import emit_volume
from holo.receive.cascade import lane_kind, scale_plan
from holo.receive.color_field import UPLIFT_ARM_FIELD, PlaneFieldConfig
from holo.receive.color_payload import collect_color_evidence
from holo.receive.color_stack import (
    UPLIFT_ARM_A3,
    UPLIFT_ARM_A4B,
    UPLIFT_ARM_OFF,
)
from holo.receive.lane_uplift import (
    UPLIFT_ARMS,
    parse_uplift_lane_id,
    uplift_lane_id,
)
from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.production_color import ProductionColorPayload
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.types import CaptureInput, RefineAddressPlan


SLOW = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the uF full-plan smokes",
)


# ---------------------------------------------------------------- the plan
def test_the_field_arm_is_the_plans_last_supplemental_lane() -> None:
    """Registered, colour-only, plane-dimensioned, and scheduled last."""
    assert UPLIFT_ARMS[-1] == UPLIFT_ARM_FIELD

    cmy8 = scale_plan(4800.0, 3, codec_family=Family.CMY8, n_streams=3)
    ladder = [row for row in cmy8
              if row.mopup_of is None and row.refine_of is None
              and row.uplift_of is None]
    uplift = [row for row in cmy8 if row.uplift_of is not None]
    assert [row.arm_override for row in uplift] == [
        UPLIFT_ARM_OFF, UPLIFT_ARM_A3, UPLIFT_ARM_A4B, UPLIFT_ARM_FIELD]
    field_lane = uplift[-1]
    # THE ORDER IS THE ARGUMENT: the field's strongest evidence tier is
    # the certified-tile probe, so it runs after every lane that could
    # still add a certificate — including the other three arms.
    assert field_lane is cmy8[-1]
    assert lane_kind(field_lane) == "uplift:field"
    finest = ladder[-1]
    assert field_lane.uplift_of == field_lane.base_lane_id == finest.lane_id
    assert (field_lane.target_ppc_num, field_lane.target_ppc_den) == (
        finest.target_ppc_num, finest.target_ppc_den)
    # Its own evidence namespace: only certificates cross lanes.
    assert field_lane.evidence_lane_id == field_lane.lane_id
    assert field_lane.lane_id == uplift_lane_id(
        finest.lane_id, UPLIFT_ARM_FIELD)
    assert parse_uplift_lane_id(field_lane.lane_id) == (
        finest.lane_id, UPLIFT_ARM_FIELD)

    # Planes, not streams: cmy7 carries one payload stream and three
    # printed planes, so it drops only the SIBLING arm.
    cmy7 = scale_plan(4800.0, 3, codec_family=Family.CMY7, n_streams=1)
    arms7 = [row.arm_override for row in cmy7 if row.uplift_of is not None]
    assert arms7 == [UPLIFT_ARM_OFF, UPLIFT_ARM_A3, UPLIFT_ARM_FIELD]

    # K is unchanged, plan for plan.
    k_plan = scale_plan(4800.0, 3, codec_family=Family.K, n_streams=1)
    assert not [row for row in k_plan if row.uplift_of is not None]
    assert scale_plan(4800.0, 3) == k_plan


# ------------------------------------------------------------- the dial
def test_only_the_field_arm_forces_the_dial() -> None:
    """The arm IS the opt-in; every other lane reads the global dial.

    ``ProductionColorPayload.plane_fields`` stays default OFF, which is
    what keeps the W2 null proof (ordinary, mop-up and refinement lanes
    on the historical ``PlaneResidual`` seam) true.
    """
    processor = ProductionColorPayload()
    assert processor.plane_fields is None
    forced = processor._arm_plane_fields(UPLIFT_ARM_FIELD)
    assert isinstance(forced, PlaneFieldConfig)
    assert forced == PlaneFieldConfig()
    for arm in (None, UPLIFT_ARM_OFF, UPLIFT_ARM_A3, UPLIFT_ARM_A4B):
        assert processor._arm_plane_fields(arm) is None

    # A sweep still owns the constants: an explicit global dial is
    # inherited by the arm rather than overwritten by the default.
    swept = PlaneFieldConfig(min_delta_dots=0.4, bandwidth_tiles=3.0)
    configured = ProductionColorPayload(plane_fields=swept)
    for arm in (None, UPLIFT_ARM_OFF, UPLIFT_ARM_FIELD):
        assert configured._arm_plane_fields(arm) is swept


def test_the_field_arm_is_not_a_stack_override() -> None:
    """It is a REGISTRATION arm: the evidence ladder never sees it.

    ``fit_region_stack`` dispatches on the three campaign names, so a
    ``field`` lane runs the standing configuration — the arm's whole
    effect lives at the registration seam, threaded independently as the
    ``plane_fields`` dial.  Pinned cell for cell against the standard
    ladder on the channel where an arm demonstrably fires (the same
    PK5 fixture the u-off baseline pin uses).
    """
    fixture = stack_fixtures.build_context_fixture(
        3.0, 0.01, row_id="c3-cmy8-p120-v0@2240x1536")

    def run(arm):
        product = collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec,
            arm_override=arm)
        return product, {
            int(window.patch_id): np.asarray(window.evidence_values)
            for window in product.windows}

    standard, standard_cells = run(None)
    field_arm, field_cells = run(UPLIFT_ARM_FIELD)
    assert standard.regions[0].context.adopted, (
        "the comparison is vacuous unless an arm actually fires here")
    assert field_cells.keys() == standard_cells.keys()
    for patch_id, values in field_cells.items():
        assert np.array_equal(values, standard_cells[patch_id]), patch_id
    assert field_arm.regions[0].context == standard.regions[0].context
    # ...and the region still names its lane's arm, so no summary from a
    # supplemental lane can be read as an ordinary one.
    assert field_arm.regions[0].uplift_arm == UPLIFT_ARM_FIELD
    assert standard.regions[0].uplift_arm == ""


# ----------------------------------------------------------- the u-leaf
def _plan_details(events):
    names = [name for name, _details in events]
    return refine_fixtures._detail_map(
        events[names.index("payload.plan")][1]), names


def test_the_field_lane_fires_on_the_residue_and_reports_its_field() -> None:
    """The leaf: committed poses, uncertified residue, field forced on.

    The lane needs no certificate frontier of its own (only A4b does) —
    it builds from whatever is there, and here four of six tiles are
    certified, so the W4 probe pass has real tier-(i) evidence to read.
    """
    spec, raster, plan, region_record, poses = (
        uplift_fixtures._cmy7_uplift_fixture())
    certified = {
        (row.page, *row.tile_yx, row.stream_id) for row in plan.certificates}
    assert certified, "the fixture must certify something to suppress"

    events: list = []
    _context, output = uplift_fixtures._run_uplift(
        spec, raster, plan, region_record, poses, UPLIFT_ARM_FIELD, events,
        refine_fixtures.LANE)
    product = output.product
    assert product is not None
    assert product.blocks and product.attempts

    details, names = _plan_details(events)
    assert details["color.uplift_arm"] == UPLIFT_ARM_FIELD
    assert details["color.plane_fields"] is True
    assert details["color.uplift_of"] == refine_fixtures.LANE
    # A supplemental lane refines no pose and mints no replacement.
    assert "pose_refine.window_progress" not in names
    assert output.replacement_address is None

    # The W5 report fires FROM THIS LANE — one per capture collection.
    field_events = [row for row in events if row[0] == "payload.plane_fields"]
    assert len(field_events) == 1
    field_details = refine_fixtures._detail_map(field_events[0][1])
    assert "plane_fields.coverage" in field_details
    for name in ("c", "m", "y"):
        assert f"plane_fields.rms_dots.{name}" in field_details

    # Monotone, measured: not one attempt on a certified stream, so every
    # certificate this lane mints is an ADD, and it carries the lane.
    lane_id = uplift_lane_id(refine_fixtures.LANE, UPLIFT_ARM_FIELD)
    attempted = {
        (row.page, *row.tile_yx, row.stream_id) for row in product.attempts}
    assert not attempted & certified
    assert all(row.lane_id == lane_id for row in product.attempts)
    assert all(row.lane_id == lane_id for row in product.blocks)
    minted = {row.attempt_id for row in product.attempts}
    assert all(row.origin_attempt_id in minted for row in product.certificates)


def test_a_fully_certified_page_never_builds_a_field() -> None:
    """The pixel-free pre-gate, inherited: no residue, no field, no cost.

    Whether the field has anything to SAY is a measurement (anchors and
    probes are both read off pixels), so the arm's cheap gate is the
    u-lane's own: nothing uncertified left ⇒ the lane commits an empty
    barrier without materializing a raster.  The margin that decides
    "nothing to say" lives per region and per plane inside the builder.
    """
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
    _context, output = uplift_fixtures._run_uplift(
        spec, sealed, plan, region_record, address_product.poses,
        UPLIFT_ARM_FIELD, u_events, refine_fixtures.LANE)
    product = output.product
    assert product is not None
    assert not product.blocks and not product.attempts
    assert not product.certificates
    assert u_events == []


def test_force_null_skips_the_field_lane_too(monkeypatch) -> None:
    """``--force-null`` means the pre-campaign receiver, EXACTLY.

    A registration arm is no more pre-campaign than a stack arm, so the
    hatch that skips u-lanes skips this one ahead of every other gate.
    """
    spec, raster, plan, region_record, poses = (
        uplift_fixtures._cmy7_uplift_fixture())
    sealed = refine_fixtures._NoPixelRaster(
        raster.source, tuple(raster.shape), raster.dpi)
    monkeypatch.setenv(uplift_fixtures.color_stack.FORCE_NULL_ENV, "1")
    events: list = []
    _context, output = uplift_fixtures._run_uplift(
        spec, sealed, plan, region_record, poses, UPLIFT_ARM_FIELD, events,
        refine_fixtures.LANE)
    product = output.product
    assert product is not None
    assert not product.blocks and not product.attempts
    assert events == []


# --------------------------------------------------- the full-plan smokes
class _RecordingColorPayload(ProductionColorPayload):
    """Every colour barrier's product, tagged with the lane that made it.

    Attempt ledgers are not durable (PLANE-FIELDS §6.1 constraint 9), so
    lane attribution is a LIVE join at commit time: this is that join's
    tap, and it changes no behaviour — ``process`` is the base class's.
    """

    ledger: list = []

    def process(self, context, survey_product, address_product):
        output = super().process(context, survey_product, address_product)
        _RecordingColorPayload.ledger.append(
            (context.lane.lane_id, output.product))
        return output


#: The smokes decode a 400-dpi capture, which is ONE rung (2 px/cell) —
#: and a u-lane binds the FINEST ordinary rung, so on a single-rung plan
#: the arm reads at the same footing the W2 dial-on smoke measured at.
#: The raster is the W2 1200-dpi render area-decimated x3, i.e. exactly
#: what the cascade derives for its own 2ppc level from that capture.
SMOKE_DPI = 400.0


def _capture_400dpi(spec, coverage) -> np.ndarray:
    rgb = w2._raster(spec, coverage)
    height = (rgb.shape[0] // 3) * 3
    width = (rgb.shape[1] // 3) * 3
    block = rgb[:height, :width].astype(np.float64).reshape(
        height // 3, 3, width // 3, 3, 3).mean(axis=(1, 3))
    return np.ascontiguousarray(np.round(block).astype(np.uint8))


def _drive(spec, raster, state_path, *, refine, defer=False):
    request = ReceiveRequest(
        spec, (CaptureInput(raster, SMOKE_DPI),), state_path=state_path,
        page_hypotheses=(0,), run_refine=refine, defer_fountain_close=defer)
    pipeline = production_pipeline(request)
    pipeline = replace(pipeline, lanes=replace(
        pipeline.lanes, payload=_RecordingColorPayload()))
    _RecordingColorPayload.ledger = []
    events: list = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        result = run_receive(
            request, pipeline=pipeline, observer=events.append)
    return result, list(_RecordingColorPayload.ledger), events


def _work_keys(state):
    return {(row.page, *row.tile_yx, row.stream_id)
            for row in state.certificates}


def _by_stream(rows):
    tally: dict[str, int] = {}
    for row in rows:
        tally[row.stream_id] = tally.get(row.stream_id, 0) + 1
    return tally


def _field_lane(spec):
    lane = scale_plan(
        SMOKE_DPI, spec.cell_dots,
        codec_family=spec.codec_family, n_streams=spec.n_streams)[-1]
    assert lane.arm_override == UPLIFT_ARM_FIELD
    return lane


@SLOW
def test_the_field_arm_recovers_the_warped_plane_on_the_residue(
    tmp_path: Path,
) -> None:
    """CLAIM 1 — the W2 dial-on gain, taken by a scheduled lane.

    Same fixture, same warp, and NO dial anywhere: the ordinary ladder
    runs exactly as it does today and loses the M certificates the
    sinusoid costs; the mop-up, refinement and three campaign-arm lanes
    all read that residue and take none of it; and the ``uF`` lane at the
    end of the tail takes all of it.

    MEASURED (2026-08-20, 400-dpi capture of the 1.35-dot M sinusoid):
    ladder 290 (C 100 / M 90 / Y 100) → whole plan 300, the whole gain
    minted by ``u00-field-2ppc-400dpi`` in 10 attempts / 7.7 s, off a
    field of 4,160 samples (1,503 certified, 998 word, 891 dust, 768
    probes over 256 certified-tile sites), M rms 0.74 dots, C/M/Y all
    adopted at coverage 1.0.
    """
    spec = w2._pooled_spec()
    payload = w2._pooled_payload()
    volume = emit_volume(spec, payload, w2._Q, tmp_path / "volume")
    coverage = w2._warp_plane(
        w2._coverage(spec, volume.pages[0].gt_path), w2.WARP_PLANE)
    raster = _capture_400dpi(spec, coverage)
    plane = w2.PLANE_NAMES[w2.WARP_PLANE]

    ladder, _ledger, _events = _drive(
        spec, raster, tmp_path / "ladder.receive.json", refine=False)
    whole, ledger, events = _drive(
        spec, raster, tmp_path / "whole.receive.json",
        refine=True, defer=True)

    # The disease is real, and the ordinary ladder still has it.
    before = ladder.state.certificates
    assert len(before) < w2.NULL_CERTIFICATES, (
        "the warped fixture stopped being degraded — the smoke proves "
        "nothing until it is")
    assert _by_stream(before)[plane] < w2.NULL_CERTIFICATES // 3

    # Monotone end to end: the whole plan is a strict superset...
    assert _work_keys(ladder.state) <= _work_keys(whole.state)
    # ...and the field arm closes the gap the sinusoid opened.
    assert len(whole.state.certificates) == w2.NULL_CERTIFICATES
    assert _by_stream(whole.state.certificates)[plane] == (
        w2.NULL_CERTIFICATES // 3)
    assert whole.payload == payload

    field_lane = _field_lane(spec)
    minted = [
        (lane_id, product) for lane_id, product in ledger
        if product is not None and product.certificates]
    assert minted, "some lane must certify something"
    field_products = [
        product for lane_id, product in minted
        if lane_id == field_lane.lane_id]
    assert field_products, (
        f"uF minted nothing: ladder {len(before)} -> "
        f"{len(whole.state.certificates)}; minting lanes "
        f"{[lane_id for lane_id, _p in minted]}")
    certificates = [
        row for product in field_products for row in product.certificates]
    assert _by_stream(certificates).get(plane, 0) > 0
    # THE DISCRIMINATING CLAIM: the whole tail gain is the field's — the
    # mop-up, refinement and three campaign arms read the same residue
    # through the same committed poses and took none of it.  A future
    # change that lets another lane take these tiles should say so here.
    assert {lane_id for lane_id, _product in minted} - {
        field_lane.lane_id} == {"l00-2ppc-400dpi"}
    assert len(certificates) == (
        len(whole.state.certificates) - len(before))

    # THE ATTRIBUTION JOIN (live, at commit): every certificate this lane
    # committed was minted by an attempt this lane made.
    attempts = {
        row.attempt_id: row
        for product in field_products for row in product.attempts}
    for row in certificates:
        assert row.origin_attempt_id in attempts
        assert attempts[row.origin_attempt_id].lane_id == field_lane.lane_id

    # The lane reports its field, and the warped plane is what it adopts.
    reports = [
        row for row in events
        if row.name == "payload.plane_fields"
        and row.context.lane_id == field_lane.lane_id]
    assert reports, "the field lane must report its field"
    details = {row.name: row.value for row in reports[-1].details}
    assert plane in str(details["plane_fields.adopted"])
    # W4's tier-(i) probes finally light up: in an ordinary lane almost
    # nothing is certified yet, and here 96.7% of the page is.
    assert int(details["plane_fields.probes"]) > 0


@SLOW
def test_the_unwarped_control_gains_nothing_and_loses_nothing(
    tmp_path: Path,
) -> None:
    """CLAIM 2 — the null cell, on the fixture with no disease.

    The W2 null proof shows the dial-off ORDINARY path is bit-identical;
    this shows the scheduled arm cannot hurt it either.  ``--complete``
    defers the close so the whole plan actually runs (a verified close
    would stop the drive before the tail), and on a page whose every
    committed span is certified the supplemental lanes pre-gate free:
    same certificate set, no field built, not one ``plane_fields`` key.
    """
    spec = w2._pooled_spec()
    payload = w2._pooled_payload()
    volume = emit_volume(spec, payload, w2._Q, tmp_path / "volume")
    raster = _capture_400dpi(
        spec, w2._coverage(spec, volume.pages[0].gt_path))

    ladder, _ledger, _events = _drive(
        spec, raster, tmp_path / "ladder.receive.json", refine=False)
    assert len(ladder.state.certificates) == w2.NULL_CERTIFICATES
    assert ladder.payload == payload

    whole, ledger, events = _drive(
        spec, raster, tmp_path / "whole.receive.json",
        refine=True, defer=True)
    field_lane = _field_lane(spec)
    opened = [
        row for row in events
        if row.name == "level.open"
        and {detail.name: detail.value for detail in row.details}.get(
            "lane.id") == field_lane.lane_id]
    assert opened, "the whole plan must reach the field lane"

    # Strict superset with equality: nothing new, nothing lost.  The
    # digest is the W2 null proof's, which pins the work keys and so
    # survives the footing change.
    assert _work_keys(whole.state) == _work_keys(ladder.state)
    assert hashlib.sha256("\n".join(sorted(
        f"{row.page}/{row.tile_yx[0]}/{row.tile_yx[1]}/{row.stream_id}"
        for row in whole.state.certificates)).encode("ascii")).hexdigest() == (
            w2.NULL_CERT_DIGEST)
    assert whole.payload == payload
    # Pre-gated free: no field was ever built, so no key was ever minted.
    assert not [
        detail for row in events for detail in row.details
        if detail.name.startswith("plane_fields")]
    assert not [row for row in events if row.name == "payload.plane_fields"]
    assert not [
        product for lane_id, product in ledger
        if lane_id == field_lane.lane_id
        and product is not None and product.attempts]
