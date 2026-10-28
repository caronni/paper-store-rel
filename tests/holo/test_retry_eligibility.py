"""Phase-7 retry150 eligibility rows (PAYLOAD-REWORK-PLAN 7.1c,
lens-coverage:06; RECEIVE-DESIGN §6.3).

Engine/records-level pins for the three §6.3 eligibility sentences that
had no direct tests:

* "a later capture may create a new evidence digest and therefore a new
  eligible frontier" — new-capture-new-frontier mints a NEW retry
  identity;
* "a newer below-floor baseline blocks tunnelling back to an older
  failure";
* "an unchanged frontier is an authoritative no-op" — identity-level, no
  CRC spend, and determinism re-derives byte-identical attempt ids across
  invocations.

Driven through ``run_attempts`` + ``RecordingLeaf`` with the REAL K
decode (``attempt_k_tile``) on corrupted tile evidence — no full
pipeline, no rasters.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from holo.core.fountain import VolumeCode
from holo.format.descriptor import FormatSpec, get_coding
from holo.gen.compose import compose_page_cells
from holo.gen.emit import source_packed_for
from holo.gen.plan import plan_volume
from holo.receive import payload
from holo.receive.evidence import AttemptStage, AttemptState
from holo.receive.evidence_blocks import EvidenceOrigin, _block_from_rows
from holo.receive.payload_engine import RecordingLeaf, run_attempts
from holo.receive.records import CertificateStore


LANE = "native"


@pytest.fixture(scope="module")
def spec() -> FormatSpec:
    spec = FormatSpec(
        get_coding("c3-r0550"), "retry-60x60", (60.0, 60.0), 0.0)
    assert spec.layout.tiles_yx == (7, 7)
    return spec


@pytest.fixture(scope="module")
def garbage_llr(spec) -> np.ndarray:
    """A genuine format tile with 25% sign flips: decodes, always fails."""
    volume_payload = hashlib.sha256(b"retry-eligibility-rows").digest()
    plan = plan_volume(spec, len(volume_payload), 0.5)
    source = source_packed_for(volume_payload, plan)
    code = VolumeCode(
        plan.k_total, plan.symbol_bits, spec.seed,
        tiles_per_page=spec.tiles_per_page)
    symbols = code.encode_symbols(
        source, np.arange(spec.tiles_per_page, dtype=np.int64))
    page = compose_page_cells(spec, 0, symbols, plan.k_total)
    tile = page[:64, :64]
    llr = (tile.astype(np.float64) * 2.0 - 1.0) * 5.0
    rng = np.random.default_rng(20260802)
    llr[rng.random(llr.shape) < 0.25] *= -1.0
    return llr


def _source(tag: str) -> str:
    return hashlib.sha256(tag.encode("ascii")).hexdigest()


def _block(llr: np.ndarray, tag: str):
    """One full-tile evidence block for capture ``tag`` at address (0,0,0)."""
    source = _source(tag)
    origin = EvidenceOrigin(f"{source}/{LANE}/patch-0", 0, 0.125)
    values = np.asarray(llr, np.float32).reshape(-1)
    return _block_from_rows(
        source, LANE, 0, (0, 0),
        ((flat, values[flat].tobytes(), origin)
         for flat in range(values.size)))


def _leaf(spec) -> RecordingLeaf:
    def decode(view, stream_id, stage):
        del stream_id
        return payload.attempt_k_tile(
            view.llr_cells_f64, spec, view.address, stage,
            source_sha256=_source("invocation"),
            lane_id=LANE,
            component_block_ids=view.component_block_ids,
            dependency_certificate_ids=view.dependency_certificate_ids)

    return RecordingLeaf(CertificateStore(spec), decode)


def _stages(rows) -> tuple[str, ...]:
    return tuple(row.stage.value for row in rows)


def test_new_capture_creates_a_new_eligible_retry_identity(
    spec, garbage_llr,
) -> None:
    block_a = _block(garbage_llr, "capture-a")

    # Invocation 1: capture A alone.  SCAN fails, retry150 runs once on
    # the same evidence digest and fails too.
    leaf_one = _leaf(spec)
    run_one = run_attempts(
        (block_a,), (block_a,), lane_id=LANE, leaf=leaf_one)
    assert _stages(run_one.attempts) == ("scan", "retry150")
    assert all(row.state is AttemptState.ATTEMPTED_FAILED
               for row in run_one.attempts)
    assert len(run_one.retry_frontier) == 1
    retry_a = run_one.attempts[1]
    assert retry_a.component_block_ids == (block_a.block_id,)

    # Invocation 2: capture B joins.  Same address, new evidence digest
    # (the two-component union) => a NEW eligible retry identity.  B flips
    # an INDEPENDENT 25%: the union stays above the informative floor
    # (~37.5% cancelled) but keeps ~6% hard errors — it decodes and fails.
    llr_b = np.array(garbage_llr, copy=True)
    rng = np.random.default_rng(7)
    llr_b[rng.random(llr_b.shape) < 0.25] *= -1.0
    block_b = _block(llr_b, "capture-b")
    leaf_two = _leaf(spec)
    run_two = run_attempts(
        (block_b,), (block_a, block_b), lane_id=LANE, leaf=leaf_two)
    assert _stages(run_two.attempts) == ("scan", "union", "retry150")
    retry_ab = run_two.attempts[-1]
    assert retry_ab.stage is AttemptStage.RETRY150
    assert set(retry_ab.component_block_ids) == {
        block_a.block_id, block_b.block_id}
    assert retry_ab.attempt_id != retry_a.attempt_id
    # The retry never tunnels past its baseline evidence: it retried the
    # newest failed baseline (the union), not the older capture-A failure.
    assert retry_ab.component_block_ids == (
        run_two.attempts[1].component_block_ids)


def test_newer_below_floor_baseline_blocks_tunnelling_to_older_failure(
    spec, garbage_llr,
) -> None:
    block_a = _block(garbage_llr, "cancel-a")
    # Capture B is the exact negation: the union view sums to all-zero
    # LLRs, which refuses BELOW the informative floor before any decode.
    block_b = _block(-garbage_llr, "cancel-b")

    leaf = _leaf(spec)
    run = run_attempts(
        (block_b,), (block_a, block_b), lane_id=LANE, leaf=leaf)
    stages = _stages(run.attempts)
    assert stages == ("scan", "union")
    scan_b, union = run.attempts
    assert scan_b.state is AttemptState.ATTEMPTED_FAILED
    assert union.state is AttemptState.BELOW_ATTEMPT_FLOOR
    assert union.syndrome_ok is None and union.crc_ok is None
    # The newest baseline for the (address, stream) is the below-floor
    # union; it is not `attempted_failed`, so NOTHING is retry-eligible —
    # tunnelling back to the older scan failure is blocked.
    assert run.retry_frontier == ()
    assert all(row.stage is not AttemptStage.RETRY150
               for row in run.attempts)


def test_unchanged_frontier_is_an_identity_level_noop(
    spec, garbage_llr,
) -> None:
    block_a = _block(garbage_llr, "noop-a")

    # Determinism across invocations: a fresh leaf over the identical
    # frontier re-derives byte-identical attempt identities and outcomes
    # (§6.3: no durable spend-once ledger — determinism delivers it).
    first = run_attempts(
        (block_a,), (block_a,), lane_id=LANE, leaf=_leaf(spec))
    second = run_attempts(
        (block_a,), (block_a,), lane_id=LANE, leaf=_leaf(spec))
    assert [row.attempt_id for row in first.attempts] == [
        row.attempt_id for row in second.attempts]
    assert [row.state for row in first.attempts] == [
        row.state for row in second.attempts]

    # Within one invocation the leaf ledger dedups the exact identity: a
    # re-drive over the unchanged frontier records NOTHING (no new attempt
    # rows, no CRC spend) — the authoritative no-op.
    leaf = _leaf(spec)
    driven = run_attempts((block_a,), (block_a,), lane_id=LANE, leaf=leaf)
    assert len(driven.attempts) == 2
    ledger_before = tuple(row.attempt_id for row in leaf.attempts)
    replay = run_attempts((block_a,), (block_a,), lane_id=LANE, leaf=leaf)
    assert replay.attempts == ()
    assert tuple(row.attempt_id for row in leaf.attempts) == ledger_before
    # With zero freshly recorded rows there is no failed baseline to
    # select either: the replay's retry frontier is empty by construction.
    assert replay.retry_frontier == ()
