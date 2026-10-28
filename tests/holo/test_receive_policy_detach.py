"""The policy-detach rule: an archived state CONTINUES under today's policy.

The id half of archive compatibility (ruled 2026-08-23), sibling of the
``--no-close`` close detach and of the plan-prefix repair.  A receiver
policy id is a readable five-component composition, so a differing id is
not opaquely foreign: the moved components are legible, and each durable
ledger belongs to exactly one of them.  ``policy_detach`` keeps
what no policy can invalidate — certificates (gate-verified against the
FORMAT) and the word-validated poses — drops the intermediates the moved
components minted, records the previous id in the state's lineage, and
refuses the two cases the model cannot detach safely.

These pins fix the whole rule: today's policy is the fixed point and
stays byte-identical, a moved payload segment drops only the evidence
pools, a moved address segment drops the search state AND stops the
retained artifacts naming it, a moved survey segment and a foreign id are
refused, an archived schema-25 file still loads, and — end to end on a
real decoded volume — a detached resume only ADDS certificates and closes
byte-exact against the never-detached control.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import _qualify_runtime_fixtures as fixtures
import _roundtrip_fixture as roundtrip
from holo.receive._runtime_validation import policy_detach
from holo.receive.observer import PolicyDetachWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.runtime_model import parse_pipeline_policy_id
from holo.receive.session import (
    STATE_MAGIC,
    SessionStatus,
    authoritative_bytes,
    detach_close,
    load_session,
    save_session,
)
from holo.receive.state_codec import authoritative_state_sha256
from holo.receive.types import CaptureInput, CloseRecord

pytestmark = pytest.mark.filterwarnings(
    "ignore::holo.receive.observer.ProvisionalReceiverWarning")

# Genuine predecessors of today's ids: the two segments every archived
# colour state in this repo actually moved (PK-FINAL and older).
OLD_SCHEDULER = "holo/phased-session/rung-major-v4-u-lanes-codingaware"
OLD_PAYLOAD = "holo/e023b-e023c-payload/paperholo-e023b-e023c-v11-pre-r-lane"
OLD_ADDRESS = "holo/production-address/v5-pre-phased-schedule"
OLD_SURVEY = "holo/e021-survey/paperholo-e021-v0"


def _policy(policy_id: str, **moved: str) -> str:
    """Rebuild one policy id with the named components replaced."""
    components = parse_pipeline_policy_id(policy_id) | moved
    return "holo/track3/kiss-v1/" + ";".join(
        f"{label}={identity}" for label, identity in components.items())


def _archive(path: Path, **moved: str):
    """Rewrite a state on disk as one minted under an OLDER policy."""
    state = load_session(path)
    archived = replace(
        state, receiver_policy_id=_policy(state.receiver_policy_id, **moved))
    save_session(path, archived, validate=False)
    return archived


def _ladder_state(tmp_path: Path, name: str) -> tuple[Path, Path]:
    """One default-bounded fixture run: a state with every ledger populated."""
    image = tmp_path / f"{name}.png"
    fixtures._write_image(image, 24_000)
    path = tmp_path / f"{name}.json"
    pipeline, _calls = fixtures._pipeline()
    run_receive(
        ReceiveRequest(fixtures._spec(), (fixtures._capture(image),), path),
        pipeline=pipeline)
    return image, path


# ---------------------------------------------------------------- unit


def test_the_five_components_round_trip_through_one_policy_id() -> None:
    pipeline, _calls = fixtures._pipeline()
    components = parse_pipeline_policy_id(pipeline.policy_id)
    assert tuple(components) == (
        "survey", "address", "payload", "scheduler", "close")
    assert _policy(pipeline.policy_id) == pipeline.policy_id
    # The scheduler component IS the live class identity, so a scheduler
    # rename is a detachable segment change and not a mystery string.
    from holo.receive.cascade import PhasedSessionScheduler
    assert components["scheduler"] == PhasedSessionScheduler.policy_id


def test_todays_policy_is_the_fixed_point(tmp_path) -> None:
    image, path = _ladder_state(tmp_path, "fixed-point")
    state = load_session(path)
    assert policy_detach(state, state.receiver_policy_id) is None
    # And a same-policy resume leaves the archived file byte-identical:
    # the detach is invisible when there is nothing to detach.
    before = path.read_bytes()
    pipeline, calls = fixtures._pipeline()
    result = run_receive(
        ReceiveRequest(fixtures._spec(), (fixtures._capture(image),), path),
        pipeline=pipeline)
    assert tuple(tuple(rows) for rows in calls) == ((), (), ())
    assert not result.state_changed
    assert path.read_bytes() == before
    assert authoritative_bytes(result.state) == authoritative_bytes(state)
    assert result.state.policy_lineage == ()


def test_a_moved_payload_segment_drops_only_the_evidence_pools(
    tmp_path,
) -> None:
    _image, path = _ladder_state(tmp_path, "payload-moved")
    state = load_session(path)
    assert state.blocks and state.poses and state.regions
    detach = policy_detach(
        state, _policy(state.receiver_policy_id, payload=OLD_PAYLOAD))
    assert detach is not None
    assert detach.segments_moved == ("payload",)
    after = detach.state
    assert after.blocks == ()
    # Everything else survives verbatim — including the search state,
    # which belongs to the address segment and did not move.
    assert after.regions == state.regions
    assert after.poses == state.poses
    assert after.proposals == state.proposals
    assert after.losers == state.losers
    assert after.parked == state.parked
    assert after.certificates == state.certificates
    assert after.captures == state.captures
    assert after.counters == state.counters
    assert after.close == state.close
    assert after.policy_lineage == (state.receiver_policy_id,)
    assert dict(detach.dropped)["evidence blocks"] == len(state.blocks)
    assert "evidence blocks" in detach.message


def test_a_moved_address_segment_drops_the_search_state(tmp_path) -> None:
    _image, path = _ladder_state(tmp_path, "address-moved")
    state = load_session(path)
    assert state.proposals and state.losers
    detach = policy_detach(
        state, _policy(state.receiver_policy_id, address=OLD_ADDRESS))
    assert detach is not None and detach.segments_moved == ("address",)
    after = detach.state
    assert (after.proposals, after.losers, after.parked) == ((), (), ())
    # The word-validated poses and their regions are physical facts.
    assert after.poses == state.poses
    assert after.regions == state.regions
    # The evidence pools belong to the payload segment, which did not move.
    assert after.blocks == state.blocks
    # No retained artifact is left naming a dropped record, and the parts
    # that survive the detach (poses, survey binding, BCH quarantine) are
    # untouched.
    for capture, original in zip(after.captures, state.captures, strict=True):
        for level, before in zip(capture.levels, original.levels, strict=True):
            if level.address is None:
                continue
            assert level.address.proposal_ids == ()
            assert level.address.loser_ids == ()
            assert level.address.parked_ids == ()
            assert level.address.pose_ids == before.address.pose_ids
            assert level.address.survey_id == before.address.survey_id
            assert level.address.bch_conflicts == before.address.bch_conflicts


def test_a_moved_survey_segment_is_refused(tmp_path) -> None:
    _image, path = _ladder_state(tmp_path, "survey-moved")
    state = load_session(path)
    with pytest.raises(ValueError, match="different survey policy"):
        policy_detach(
            state, _policy(state.receiver_policy_id, survey=OLD_SURVEY))


@pytest.mark.parametrize("policy_id", [
    "holo/e023c/some-other-receiver",
    "holo/track3/kiss-v1/survey=s;address=a;payload=p;close=c",
    "holo/track3/kiss-v1/survey=s;address=a;payload=p;close=c;scheduler=x",
    "holo/track3/kiss-v1/survey=s;address=;payload=p;scheduler=x;close=c",
])
def test_an_unreadable_policy_id_is_refused(tmp_path, policy_id) -> None:
    _image, path = _ladder_state(tmp_path, "foreign")
    state = load_session(path)
    with pytest.raises(ValueError, match="receiver policy id"):
        policy_detach(state, policy_id)
    with pytest.raises(ValueError, match="receiver policy id"):
        policy_detach(replace(state, receiver_policy_id=policy_id),
                      state.receiver_policy_id)


def test_an_archived_schema_25_state_loads_with_an_empty_lineage(
    tmp_path,
) -> None:
    """The migration the ruling exists for: the archive predates the field."""
    _image, path = _ladder_state(tmp_path, "schema-25")
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["schema_version"] == 26
    document = {
        key: value for key, value in envelope["state"].items()
        if key != "policy_lineage"}
    legacy = {
        "magic": STATE_MAGIC,
        "schema_version": 25,
        "state": document,
        "state_sha256": authoritative_state_sha256(
            document, magic=STATE_MAGIC, schema=25),
    }
    path.write_text(
        json.dumps(legacy, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False) + "\n",
        encoding="utf-8")

    loaded = load_session(path)
    assert loaded.policy_lineage == ()
    assert loaded == load_session(path)
    # A schema-25 file is READ, never written: the rewrite happens only
    # when a barrier legitimately saves.
    assert json.loads(path.read_text(encoding="utf-8"))[
        "schema_version"] == 25

    # An undeclared older version, and anything NEWER than this tree
    # writes, still refuse.
    for version, expected in ((3, "no migration is declared from 3"),
                              (99, "magic or schema is unsupported")):
        legacy["schema_version"] = version
        legacy["state_sha256"] = authoritative_state_sha256(
            document, magic=STATE_MAGIC, schema=version)
        path.write_text(
            json.dumps(legacy, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n",
            encoding="utf-8")
        with pytest.raises(ValueError, match=expected):
            load_session(path)


def test_every_declared_migration_is_an_additive_default() -> None:
    """The migration doctrine, stated as an executable rule.

    A step supplies the keys a later field set added, at the dataclass
    default, and rewrites nothing that was stored.  Anything that needs
    more is a new state identity, not a migration.
    """
    from holo.receive.discovery_state import DISCOVERY_MIGRATIONS
    from holo.receive.session import STATE_MIGRATIONS

    session_doc = {"format_row_id": "row", "receiver_policy_id": "policy",
                   "certificates": [{"certificate_id": "c"}]}
    lifted = STATE_MIGRATIONS[25](session_doc)
    assert lifted == {**session_doc, "policy_lineage": []}
    # The discovery root IS a tuple of session branches, so its own
    # migration is the same step applied per branch.
    root = {"discovery_policy_id": "d", "branches": [dict(session_doc)],
            "surveys": []}
    discovery = DISCOVERY_MIGRATIONS[11](root)
    assert discovery["branches"] == [lifted]
    assert discovery["surveys"] == root["surveys"]
    assert discovery["discovery_policy_id"] == "d"
    # Additive only: no step drops or rewrites a stored key.
    for before, after in ((session_doc, lifted), (root, discovery)):
        for key, value in before.items():
            if key == "branches":
                continue
            assert after[key] == value


# ------------------------------------------------------------- runtime


def test_an_old_policy_state_resumes_into_the_appended_lanes(
    tmp_path,
) -> None:
    image, path = _ladder_state(tmp_path, "resume")
    spec = fixtures._spec()
    archived = _archive(
        path, payload=OLD_PAYLOAD, scheduler=OLD_SCHEDULER)
    committed = len(archived.captures[0].levels)
    assert committed < len(archived.captures[0].plan)  # a tail is owed

    pipeline, calls = fixtures._pipeline()
    with pytest.warns(PolicyDetachWarning, match="payload, scheduler moved"):
        result = run_receive(
            ReceiveRequest(spec, (fixtures._capture(image),), path,
                           run_refine=True),
            pipeline=pipeline)

    resumed = result.state
    assert resumed.receiver_policy_id == pipeline.policy_id
    assert resumed.policy_lineage == (archived.receiver_policy_id,)
    # The retained prefix was never re-run; the owed tail was.
    driven = len(resumed.captures[0].levels) - committed
    assert driven > 0
    assert result.captures[0].barriers_committed == driven
    assert len(calls[0]) == driven
    # Monotone: no certificate is ever lost by a detach.
    assert {row.certificate_id for row in resumed.certificates} >= {
        row.certificate_id for row in archived.certificates}
    assert len(resumed.poses) >= len(archived.poses)
    # The detached state is what got persisted.
    assert load_session(path).policy_lineage == (
        archived.receiver_policy_id,)


def test_a_terminal_old_policy_state_composes_with_the_close_detach(
    tmp_path,
) -> None:
    """--no-close on an archived terminal state: BOTH detaches apply."""
    fixture = roundtrip._build_fixture()
    spec = fixture.spec
    path = tmp_path / "terminal.state"
    captures = (CaptureInput(fixture.raster, roundtrip._DPI),)
    verified = _decode(spec, captures, path, finalize=True)
    assert verified.status is SessionStatus.VERIFIED

    archived = _archive(path, payload=OLD_PAYLOAD, scheduler=OLD_SCHEDULER)
    assert archived.status is SessionStatus.VERIFIED
    with pytest.warns(PolicyDetachWarning):
        reopened = _decode(spec, captures, path, finalize=False)
    assert reopened.status is SessionStatus.OPEN
    assert reopened.close == CloseRecord()
    assert reopened.policy_lineage == (archived.receiver_policy_id,)
    assert {row.certificate_id for row in reopened.certificates} >= {
        row.certificate_id for row in archived.certificates}
    # The two detaches are independent derivations that compose in either
    # reading: detaching the close of the detached state is a fixed point.
    assert detach_close(reopened) is reopened


def test_a_detached_resume_closes_byte_exact_against_the_control(
    tmp_path,
) -> None:
    """The e2e promise: continuing under a new policy changes no bytes."""
    fixture = roundtrip._build_fixture()
    spec = fixture.spec
    captures = (CaptureInput(fixture.raster, roundtrip._DPI),)
    control_path = tmp_path / "control.state"
    detached_path = tmp_path / "detached.state"
    for path in (control_path, detached_path):
        open_state = _decode(spec, captures, path, finalize=False)
        assert open_state.status is SessionStatus.OPEN
        assert open_state.certificates

    archived = _archive(
        detached_path, payload=OLD_PAYLOAD, scheduler=OLD_SCHEDULER)
    control_run = _run(spec, captures, control_path, finalize=True)
    with pytest.warns(PolicyDetachWarning):
        detached_run = _run(spec, captures, detached_path, finalize=True)
    control, detached = control_run.state, detached_run.state

    assert control.status is SessionStatus.VERIFIED
    assert detached.status is SessionStatus.VERIFIED
    assert detached.close == control.close
    assert detached_run.payload == fixture.payload == control_run.payload
    assert {row.certificate_id for row in detached.certificates} >= {
        row.certificate_id for row in archived.certificates}
    assert detached.policy_lineage == (archived.receiver_policy_id,)
    # The ONLY durable difference to the never-detached control is the
    # lineage the detach recorded.
    assert authoritative_bytes(
        replace(detached, policy_lineage=())) == authoritative_bytes(control)


def _run(spec, captures, state_path: Path, *, finalize: bool):
    request = ReceiveRequest(
        spec, captures, state_path=state_path, page_hypotheses=(0,),
        defer_fountain_close=True)
    return run_receive(
        request, pipeline=production_pipeline(request),
        finalize_deferred_close=finalize)


def _decode(spec, captures, state_path: Path, *, finalize: bool):
    return _run(spec, captures, state_path, finalize=finalize).state
