from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

import numpy as np
import pytest

from holo.receiver import data
from holo.receiver.tests import _h3_decode_diff, _h3_fixture_build

def _record(label: str = "color-w1", workers: int = 1,
            argv_extra: tuple[str, ...] = (), seed: int = 7,
            ) -> dict[str, object]:
    """A record shaped exactly as the cache stores it, from seeded bits."""
    rng = np.random.default_rng(seed)
    certificates = {}
    for ty, tx, stream in ((0, 0, "C"), (0, 1, "M"), (1, 0, "Y"),
                           (1, 1, "C")):
        key = (0, ty, tx, stream)
        certificates[key] = data.Certificate(
            0, ty, tx, stream, rng.integers(0, 2, 64, dtype=np.uint8),
            "tiles/scan")
    payload = bytes(rng.integers(0, 256, 32, dtype=np.uint8))
    record = {name: None for name in _h3_fixture_build._CACHED_FIELDS}
    record.update(
        label=label, workers=workers,
        argv=("decode", "sim.tif", "--workers", str(workers),
              *argv_extra),
        exit_code=0, status="verified", payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        certified=len(certificates), certificates=certificates,
        certificate_signature=_h3_fixture_build._certificate_signature(
            certificates),
        attempt_outcomes={
            (0, ty, tx, stream, "scan", ("cap", 0)): "certified"
            for (_page, ty, tx, stream) in certificates})
    return record


def _copy(record: dict[str, object]) -> dict[str, object]:
    return pickle.loads(pickle.dumps(record))


def _flip_certificate_bit(record: dict[str, object], key: tuple,
                          bit: int) -> dict[str, object]:
    mutated = _copy(record)
    certificates = dict(mutated["certificates"])
    standing = certificates[key]
    bits = np.asarray(standing.user_bits, np.uint8).copy()
    bits[bit] ^= 1
    certificates[key] = data.Certificate(
        standing.page, standing.ty, standing.tx, standing.stream_id, bits,
        standing.source)
    mutated["certificates"] = certificates
    mutated["certificate_signature"] = (
        _h3_fixture_build._certificate_signature(certificates))
    return mutated


def _publish(root: Path, render_key: str, decode_key: str,
             record: dict[str, object]) -> None:
    entry = root / render_key / "decodes" / decode_key
    entry.mkdir(parents=True)
    (entry / _h3_fixture_build._CACHED_RECORD).write_bytes(
        pickle.dumps(record))


@pytest.mark.parametrize("workers,argv_extra,exact", [
    (1, (), True), (8, ("--complete",), False), (8, (), False)])   # --complete at 8 workers: pooled (measured 2026-10-12)
def test_a_record_against_its_own_copy_is_identical(workers, argv_extra,
                                                    exact):
    record = _record(workers=workers, argv_extra=argv_extra)
    diff = _h3_decode_diff.diff_records(record, _copy(record))
    assert diff.identical, diff.differences
    assert diff.deterministic is exact


@pytest.mark.parametrize("workers", [1, 8])
def test_a_mutated_certificate_differs_and_is_named(workers):
    record = _record(workers=workers)
    mutated = _flip_certificate_bit(record, (0, 1, 0, "Y"), 17)
    diff = _h3_decode_diff.diff_records(record, mutated)
    assert not diff.identical
    assert diff.differences == (
        "certificate (0, 1, 0, 'Y'): user bit 17 differs",)


def test_the_first_differing_certificate_is_the_first_in_key_order():
    record = _record()
    mutated = _flip_certificate_bit(
        _flip_certificate_bit(record, (0, 1, 1, "C"), 3), (0, 0, 1, "M"), 9)
    diff = _h3_decode_diff.diff_records(record, mutated)
    assert diff.differences == (
        "certificate (0, 0, 1, 'M'): user bit 9 differs",)


def test_a_deterministic_record_differs_on_a_missing_certificate():
    record = _record(workers=1)
    fewer = _copy(record)
    fewer["certificate_signature"] = record["certificate_signature"][1:]
    diff = _h3_decode_diff.diff_records(record, fewer)
    assert diff.differences == ("certificate (0, 0, 0, 'C') only in base",)


def test_a_pooled_record_compares_only_the_certificates_both_sides_hold():
    record = _record(workers=8)
    fewer = _copy(record)
    fewer["certificate_signature"] = record["certificate_signature"][1:]
    assert _h3_decode_diff.diff_records(record, fewer).identical


@pytest.mark.parametrize("workers,exact", [(1, True), (8, False)])
def test_an_attempt_outcome_differs_only_in_a_deterministic_record(
        workers, exact):
    record = _record(workers=workers)
    moved = _copy(record)
    key = next(iter(moved["attempt_outcomes"]))
    moved["attempt_outcomes"][key] = "attempted_failed"
    diff = _h3_decode_diff.diff_records(record, moved)
    if exact:
        assert len(diff.differences) == 1
        assert diff.differences[0].startswith(f"attempt {key}:")
    else:
        assert diff.identical


@pytest.mark.parametrize("field,value", [
    ("status", "not-verified"), ("exit_code", 2),
    ("payload_sha256", "0" * 64)])
def test_an_outcome_field_differs_in_either_class(field, value):
    for workers in (1, 8):
        record = _record(workers=workers)
        diff = _h3_decode_diff.diff_records(record, {**record, field: value})
        assert len(diff.differences) == 1
        assert diff.differences[0].startswith(f"{field}: ")


def test_two_caches_pair_by_label_and_a_one_sided_label_differs(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    _publish(base, "r0", "d1", _record("k-w1", seed=1))
    _publish(base, "r0", "d2", _record("color-w8", workers=8, seed=2))
    _publish(base, "r0", "d3", _record("only-base", seed=3))
    _publish(head, "r9", "e1", _record("k-w1", seed=1))
    _publish(head, "r9", "e2", _record("color-w8", workers=8, seed=2))
    (head / "r9" / "decodes" / ".e3.123").mkdir()
    (head / "r9" / "decodes" / ".e3.123" / "record.pkl").write_bytes(
        pickle.dumps(_record("staging", seed=4)))
    diffs = _h3_decode_diff.diff_caches(base, head)
    assert [(d.label, d.identical) for d in diffs] == [
        ("color-w8", True), ("k-w1", True), ("only-base", False)]
    assert diffs[2].differences == ("only in base",)
    assert _h3_decode_diff.main([str(base), str(base)]) == 0
    assert _h3_decode_diff.main([str(base), str(head)]) == 1


def test_a_cache_that_has_seen_two_trees_is_refused(tmp_path):
    _publish(tmp_path, "r0", "d1", _record("k-w1"))
    _publish(tmp_path, "r0", "d2", _record("k-w1"))
    with pytest.raises(ValueError, match="fresh HOLO3_FIXTURE_CACHE"):
        _h3_decode_diff.load_records(tmp_path)


def test_two_empty_caches_are_no_null(tmp_path):
    with pytest.raises(ValueError, match="no null"):
        _h3_decode_diff.diff_caches(tmp_path, tmp_path)


def test_the_tool_reads_the_fields_the_cache_stores():
    stored = set(_h3_fixture_build._CACHED_FIELDS)
    assert {"label", "workers", "argv", "certificate_signature",
            "attempt_outcomes", *_h3_decode_diff.OUTCOME_FIELDS} <= stored


def test_a_live_decode_record_reads_as_the_cache_stores_it(tmp_path):
    record = _record()
    live = _h3_fixture_build.DecodeRecord(
        run_dir=tmp_path / "run", out_path=tmp_path / "payload.bin",
        **record)
    fields = _h3_decode_diff.record_fields(live)
    assert set(fields) == set(_h3_fixture_build._CACHED_FIELDS)
    assert _h3_decode_diff.diff_records(fields, record).identical
