"""Pins ``holo2/measure/tile_differential.py`` on a two-tile fixture pair.

Lives here (not ``holo2/tests``) for the same reason ``test_v1_parity.py``
does: it is one of the two places allowed to import ``holo`` (RULINGS §F
carries the pre-existing rule the KISS-branch memory states — "only
``tests/holo2_oracles/`` + ``measure/verdicts/test_v1_parity.py`` may
import v1"). Self-contained: it builds its own minimal v1
``SessionState`` and its own minimal holo2 ``Store`` rather than reaching
into ``holo2/tests/conftest.py`` (a different pytest root — pytest's
``pythonpath`` ini only names ``src``/``holo2/src``, not
``holo2/tests``, so importing that module's builders here would need its
own path surgery for no real saving; the two builders below are a dozen
lines each).

THE FORK THIS PINS: a differential that (a) confused "no record" with
"attempted and failed" — i.e. read ``TileState`` off attempted-ness
alone instead of gating it behind a durable record existing first
(``tilemap.tile_state``'s own rule) — or (b) swapped which SIDE's
certificate set it read when computing the two one-sided differences,
would still report a plausible-looking two-tile diff on a real sheet
(both mistakes are silent on any corpus where "record exists" and
"was attempted" happen to coincide, which is the common case). The
fixture below is built so the two are NOT coincident on one of its two
certified-diff tiles (a spend is recorded only after a placement writes
the tile's first ``observed_by``, mirroring the real pipeline's order,
so getting the gate backwards changes tile (0, 0)'s rank) and so the
two certificate sets are asymmetric (v1 certifies (0, 0) only, holo2
certifies (0, 1) only) — a swapped-side differential reports the two
lists exactly reversed, which every assertion below would catch.

Fork (a) needs a THIRD tile, not just tile (0, 0): a fixture where every
``TileRecord`` that exists was also attempted, and every attempt has a
record, cannot distinguish "gate off attempted-ness first" from "gate
off a durable record first" — both readings agree everywhere. Tile
(0, 1, 0) below has a record and an UN-attempted (``exposures=0``)
``below_floor`` spend, so it must read ADDRESSED, not ATTEMPTED — the
headline rank whose count is 0 on both real sheets in ``HANDOFF-W1.md``
§3, and the class this fixture previously never exercised. Tile
(0, 1, 1) has an attempted (``exposures=1``) spend but NO ``TileRecord``
at all (a spend can be durable while its tile's ledger key was never
written, since the two live in different families) — it must read
UNKNOWN, not ATTEMPTED: a rank-off-attempted-ness-first mutant returns
ATTEMPTED here since it never asks "does a record exist" before
"was it attempted"; ``tilemap.tile_state``'s real rule asks record-
existence first and returns UNKNOWN regardless. Verified by injecting
that exact mutant and re-running this file: it survived before these
two tiles existed and fails now.

Two more facts get pinned along the way because they were exercised for
free once the fixture existed: v1's LANE/FOOTING attribution (via
``holo.receive.cascade.lane_kind`` over the pose that covers a tile) and
v1's RETAINED-EVIDENCE-BLOCK margin (min/mean |LLR| off
``EvidenceBlock.printed_llr_f32`` directly, no bitmap/origin decoding).
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_ROOT / "src", _ROOT / "holo2" / "src",
             _ROOT / "holo2" / "measure"):
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

from holo.receive.evidence import TileCertificateRecord           # noqa: E402
from holo.receive.evidence_blocks import EvidenceBlock, EvidenceOrigin  # noqa: E402
from holo.receive.session_model import CaptureRecord as V1Capture  # noqa: E402
from holo.receive.session_model import SessionState                # noqa: E402
from holo.receive.types import LaneSpec, PoseRecord as V1Pose      # noqa: E402

import tile_differential as td                                    # noqa: E402

from holo2.capture import CaptureRecord, FootingSpec, RegionRecord  # noqa: E402
from holo2.capture import capture_key, region_key                  # noqa: E402
from holo2.cli import record_registry                              # noqa: E402
from holo2.core import Store                                       # noqa: E402
from holo2.core.commit import CommitBatch, CommitEngine, Write     # noqa: E402
from holo2.core.identity import SpendRecord                        # noqa: E402
from holo2.core.keys import WorkId, WorkScope                      # noqa: E402
from holo2.engine import RECIPE_V1                                  # noqa: E402
from holo2.engine.records import SessionIdentity                    # noqa: E402
from holo2.solve import (CalibrationRecord, EvidenceObservation,   # noqa: E402
                         HeldoutGate, MintRef, PoseRecord, TileRecord,
                         TileState, WindowRecord, WindowStatus,
                         calibration_key, evidence_key, pack_observed_cells,
                         pose_key, tile_key, window_key)
from holo2.solve.payload import FAMILY_PAYLOAD                     # noqa: E402

_V1_CAPTURE_SHA = "ab" * 32
_H2_CAPTURE_SHA = "cd" * 32
_H2_FOOTING = f"{_H2_CAPTURE_SHA[:12]}:2/1"
_TILES_YX = (2, 3)   # third column stays wholly untouched (both UNKNOWN)


def _v1_state() -> SessionState:
    """One lane, two poses (tiles (0,0) and (0,1)), one certificate at
    (0,0), one retained evidence block at (0,1)."""
    lane = LaneSpec(lane_id="l00", target_ppc_num=2, target_ppc_den=1,
                    native_per_view_num=1, native_per_view_den=1)
    capture = V1Capture(source_sha256=_V1_CAPTURE_SHA, dpi=600.0,
                        dtype="uint8", shape_yx=(100, 100), channels=1,
                        plan=(lane,), levels=())

    def pose(window_id: int, cell_origin_yx: tuple[int, int]) -> V1Pose:
        return V1Pose(
            pose_id="cd" * 32, capture_id=_V1_CAPTURE_SHA, lane_id="l00",
            region_id="r0", patch_id=0, placement_outcome="accepted",
            page=0, cell_origin_yx=cell_origin_yx,
            native_affine=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0), rot90=0,
            quality=1.0, window_id=window_id, window_origin_yx_px=(0, 0),
            window_shape_yx_cells=(64, 64), window_depth=0,
            lane_pose_origin_yx=(0.0, 0.0),
            lane_pose_jacobian=(1.0, 0.0, 0.0, 1.0),
            lane_pose_phase_yx=(0.0, 0.0), lane_pose_pitch_px=1.0,
            lane_pose_angle_deg=0.0, segment_support_cells=10,
            segment_phase_contrast=0.5, segment_pitch_yx_px=(1.0, 1.0),
            segment_orthogonality_error_deg=0.0)

    certificate = TileCertificateRecord(
        certificate_id="ef" * 32, page=0, tile_yx=(0, 0),
        packed_user_bits=b"\x01", origin_attempt_id="attempt-a")

    bitmap = bytearray(512)
    bitmap[0] = 0b11000000     # two observed cells, MSB-first
    block = EvidenceBlock(
        source_sha256=_V1_CAPTURE_SHA, lane_id="l00", page=0, tile_yx=(0, 1),
        observed_bitmap=bytes(bitmap),
        printed_llr_f32=np.array([1.5, -0.25], "<f4").tobytes(),
        origin_indices_u16=np.array([0, 0], "<u2").tobytes(),
        origins=(EvidenceOrigin("p-1", 0, 0.1),),
        content_sha256=b"\x11" * 32, kind="k")

    return SessionState(
        format_row_id="fixture@2x2", receiver_policy_id="policy-test",
        page_hypotheses=(0,), captures=(capture,),
        poses=(pose(1, (0, 0)), pose(2, (0, 64))),
        certificates=(certificate,), blocks=(block,))


def _build_h2_store(state_dir: Path) -> None:
    """One capture/region/calibration, two windows/poses (tiles (0,0)
    and (0,1)), an ATTEMPTED-FAILED spend at (0,0) and a CERTIFIED tile
    at (0,1) — the mirror image of the v1 state above. Plus two more
    tiles that carry no v1 side at all (this fixture's certificate-set
    diff does not involve them) but exercise the two ranks the two-tile
    version above never reached: tile (0,1,0) is ADDRESSED (a record,
    an un-attempted below_floor spend) and tile (0,1,1) is UNKNOWN
    despite an attempted spend (no record was ever written for it) —
    see the module docstring's "THE FORK THIS PINS" for why both matter.
    Tile (0,1,2) stays wholly untouched (both sides UNKNOWN, no spend).
    """
    session = SessionIdentity(
        format_row_id="fixture@2x2", receiver_policy_id="policy-test",
        recipe_entries=RECIPE_V1.entries, providers=("fixture-v0",),
        page_domain=(0,))
    registry = record_registry(page_domain=(0,))
    region = region_key(_H2_CAPTURE_SHA, (0, 0), 8, (128, 128))
    window0 = window_key(_H2_FOOTING, region, (0, 0, 64, 64))
    pose0 = pose_key(window0, 0, (1.0, 0.0, 0.0, 0.0, 1.0, 0.0))
    key0 = tile_key(0, 0, 0, "main")
    window1 = window_key(_H2_FOOTING, region, (0, 64, 64, 128))
    pose1 = pose_key(window1, 0, (1.0, 0.0, 64.0, 0.0, 1.0, 0.0))
    key1 = tile_key(0, 0, 1, "main")
    ev1 = evidence_key(_H2_FOOTING, 0, 0, 1, "main", pose1)
    key2 = tile_key(0, 1, 0, "main")     # ADDRESSED: record, no attempt
    key3 = tile_key(0, 1, 1, "main")     # UNKNOWN: attempt, no record

    with Store.create(state_dir, session, registry) as store:
        engine = CommitEngine(store)
        mask_ref = store.put_array(np.zeros(4, np.uint8))
        params_ref = store.put_array(np.zeros(2, np.float64))
        calibration = calibration_key(window1, "pava-v1", params_ref.sha256)
        llr_ref = store.put_array(np.zeros(4096, np.float32))
        observed_ref = store.put_array(
            pack_observed_cells(np.ones((64, 64), bool)))
        engine.apply(CommitBatch(writes=(
            Write(capture_key(_H2_CAPTURE_SHA), CaptureRecord(
                source_sha256=_H2_CAPTURE_SHA, dpi_true=600.0,
                shape_px=(128, 128), dtype="uint8", channels=1,
                platen_backing=200.0,
                footings=(FootingSpec(_H2_FOOTING, Fraction(2, 1), _H2_CAPTURE_SHA),))),
            Write(region, RegionRecord(
                capture_sha256=_H2_CAPTURE_SHA, support_mask_ref=mask_ref,
                pitch_in_vote=Fraction(1, 100),
                support_origin_px=(0, 0), support_step_px=8,
                support_extent_px=(128, 128))),
            Write(calibration, CalibrationRecord(
                scope=window1, algorithm="pava-v1", params_ref=params_ref,
                heldout=HeldoutGate(adopted=True, logloss_delta=-0.01))),
            # window0/pose0/tile0: a placement observed the tile but no
            # decoder has certified it yet — the realistic precondition
            # for a payload spend (a spend never precedes its tile's
            # first ``observed_by`` in the real pipeline).
            Write(window0, WindowRecord(
                footing_id=_H2_FOOTING, region_id=region,
                extent_cells=(0, 0, 64, 64), status=WindowStatus.ACTIVE)),
            Write(pose0, PoseRecord(
                window_id=window0, footing_id=_H2_FOOTING, page=0,
                native_affine=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0))),
            Write(key0, TileRecord(observed_by=(_H2_FOOTING,))),
            # window1/pose1/tile1: certified.
            Write(window1, WindowRecord(
                footing_id=_H2_FOOTING, region_id=region,
                extent_cells=(0, 64, 64, 128), status=WindowStatus.ACTIVE)),
            Write(pose1, PoseRecord(
                window_id=window1, footing_id=_H2_FOOTING, page=0,
                native_affine=(1.0, 0.0, 64.0, 0.0, 1.0, 0.0))),
            Write(ev1, EvidenceObservation(
                footing_id=_H2_FOOTING, page=0, ty=0, tx=1, stream="main",
                pose_id=pose1, llr_ref=llr_ref, observed_ref=observed_ref,
                calibration_id=calibration)),
            Write(key1, TileRecord(
                minting=MintRef(pose1, "scan", "fixture-decoder"),
                observed_by=(_H2_FOOTING,))),
            # key2: a record exists (a placement observed it) but the
            # one spend against it never ran a decoder (exposures=0) —
            # ADDRESSED, not ATTEMPTED.
            Write(key2, TileRecord(observed_by=(_H2_FOOTING,))),
            # key3: deliberately NO TileRecord write — only a spend.
        )))
        engine.apply(CommitBatch(spends=(
            SpendRecord(
                worker_id=WorkId(FAMILY_PAYLOAD, key0, "scan",
                                 WorkScope(profile=_H2_FOOTING)),
                route="scan", identity=((key0, 1),), outcome="crc_failed",
                attempts=1, exposures=1),
            SpendRecord(
                worker_id=WorkId(FAMILY_PAYLOAD, key2, "scan",
                                 WorkScope(profile=_H2_FOOTING)),
                route="scan", identity=((key2, 1),), outcome="below_floor",
                attempts=1, exposures=0),
            SpendRecord(
                worker_id=WorkId(FAMILY_PAYLOAD, key3, "scan",
                                 WorkScope(profile=_H2_FOOTING)),
                route="scan", identity=((key3, 1),), outcome="crc_failed",
                attempts=1, exposures=1),
        )))


def test_differential_attributes_the_known_two_tile_fork(
        tmp_path: Path) -> None:
    state_dir = tmp_path / "h2-state"
    _build_h2_store(state_dir)
    v1_index = td.build_v1_index(_v1_state(), _TILES_YX)

    with td.open_h2_store(state_dir) as store:
        h2_index = td.build_h2_index(store)
        report = td.differential(v1_index, store, h2_index, _TILES_YX,
                                 (0,), stream="main", label="fixture",
                                 format_ref="fixture@2x2")

        # (A) the sets and their differences.
        assert report.v1_certified == 1
        assert report.h2_certified == 1
        assert report.both == ()
        assert report.neither == 4
        assert report.total_tiles == 6

        # (B) v1 has (0, 0), holo2 lacks it: attempted, crc_failed, off
        # the durable spend ledger, and NOT confused with never-having-
        # a-record (the fork this test exists to catch).
        assert [diff.key for diff in report.v1_only] == [(0, 0, 0)]
        v1_only = report.v1_only[0]
        assert v1_only.h2_state is TileState.ATTEMPTED
        assert len(v1_only.h2_spends) == 1
        assert v1_only.h2_spends[0].outcome == "crc_failed"
        assert v1_only.h2_spends[0].route == "scan"
        assert len(v1_only.v1_poses) == 1
        assert v1_only.v1_poses[0].lane_kind == "ordinary"
        assert v1_only.v1_poses[0].footing_ppc == "2/1"

        # (C) holo2 has (0, 1), v1 lacks it: certified in holo2, and v1
        # still shows the covering pose (lane attribution) AND the
        # retained (uncertified-in-v1) evidence block with its LLR
        # margin, computed with no bitmap/origin decoding.
        assert [diff.key for diff in report.h2_only] == [(0, 0, 1)]
        h2_only = report.h2_only[0]
        assert h2_only.h2_state is TileState.CERTIFIED
        assert len(h2_only.v1_poses) == 1
        assert h2_only.v1_poses[0].lane_id == "l00"
        assert len(h2_only.v1_blocks) == 1
        assert h2_only.v1_blocks[0].n_observed == 2
        assert h2_only.v1_blocks[0].min_abs_llr == pytest.approx(0.25)
        assert h2_only.v1_blocks[0].mean_abs_llr == pytest.approx(0.875)
        assert len(h2_only.h2_poses) == 1
        assert h2_only.h2_poses[0].footing_id == _H2_FOOTING
        assert h2_only.h2_poses[0].window_status == "active"

        # (D) the summary table agrees with the per-tile classification.
        table = td.summary_table(report)
        assert "v1-only: holo2 ATTEMPTED-FAILED | 1 |" in table
        assert "holo2-only: v1 retains uncertified evidence | 1 |" in table

        # a genuinely untouched tile classifies NEVER-ADDRESSED on both
        # sides — the third rank the fork above could also have hidden.
        state, spends, poses = td.h2_tile_facts(store, h2_index, 0, 1, 2,
                                                "main")
        assert state is TileState.UNKNOWN
        assert spends == ()
        assert poses == ()
        assert v1_index.coverage.get((0, 1, 2), []) == []

        # ADDRESSED: a record exists, but its one spend never ran a
        # decoder (exposures=0) — the class the mutant this test is
        # built to catch cannot reach, because it never distinguishes
        # ADDRESSED from ATTEMPTED at all (it reads attempted-ness
        # first and only falls through to "no record" after).
        state2, spends2, _ = td.h2_tile_facts(store, h2_index, 0, 1, 0,
                                              "main")
        assert state2 is TileState.ADDRESSED
        assert len(spends2) == 1
        assert spends2[0].outcome == "below_floor"
        assert spends2[0].exposures == 0

        # UNKNOWN despite an attempted (exposures=1) spend, because no
        # TileRecord was ever written for this key — THE fork this test
        # exists to catch: a differential that reads TileState off
        # attempted-ness alone (instead of gating behind a durable
        # record first) reports this tile ATTEMPTED instead.
        state3, spends3, _ = td.h2_tile_facts(store, h2_index, 0, 1, 1,
                                              "main")
        assert state3 is TileState.UNKNOWN
        assert len(spends3) == 1
        assert spends3[0].outcome == "crc_failed"
        assert spends3[0].exposures == 1


def test_render_report_does_not_raise(tmp_path: Path) -> None:
    """The markdown renderer runs over both directions without crashing —
    the one thing a per-tile classification test cannot catch on its own
    (a formatter that raises on an empty tuple, say)."""
    state_dir = tmp_path / "h2-state"
    _build_h2_store(state_dir)
    v1_index = td.build_v1_index(_v1_state(), _TILES_YX)
    with td.open_h2_store(state_dir) as store:
        h2_index = td.build_h2_index(store)
        report = td.differential(v1_index, store, h2_index, _TILES_YX,
                                 (0,), stream="main", label="fixture",
                                 format_ref="fixture@2x2")
    text = td.render_report(report)
    assert "page 0, tile (0, 0)" in text
    assert "page 0, tile (0, 1)" in text
