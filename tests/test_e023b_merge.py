"""Fail-closed contracts for the E023b certificate-boundary merge."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023b-integrated-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

from paperholo import payloaddec, receiver  # noqa: E402
import merge_e023b  # noqa: E402
import test_e023b_algorithm_arms as arms_test  # noqa: E402
import test_e023b_session as session_test  # noqa: E402


@pytest.fixture(scope="module")
def base_state(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("e023b-merge")
    descriptor, upstream, image, _user, _framed = session_test._fixture(
        tmp_path)
    session = receiver.ReceiverSession.create(
        descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(
        session, session_test._record(
            descriptor, upstream.scans[0], image))
    path = tmp_path / "base.pkl"
    receiver.save_session(path, session)
    return path, session


def _variant(session, path: Path, *, demote: bool = False,
             flip_certificate: bool = False,
             truncate_certificate: bool = False,
             capture_id: str | None = None,
             dpi: float | None = None):
    working = session.fork()
    if dpi is not None:
        working.envelope = replace(working.envelope, dpi=float(dpi))
    working.scans = [
        replace(
            scan,
            source_path=str(path.with_suffix(".tiff").resolve()),
            capture_id=(scan.capture_id if capture_id is None else capture_id),
            dpi=(scan.dpi if dpi is None else float(dpi)))
        for scan in working.scans
    ]
    if capture_id is not None:
        working.attempts = [
            replace(row, capture_ids=tuple(
                capture_id for _old in row.capture_ids))
            for row in working.attempts
        ]
    if demote:
        working, _key, _parent = arms_test._demote_one_certificate(working)
    if flip_certificate:
        outcome = next(
            row for row in working.decode.tiles.values()
            if row.state == "certified")
        outcome.user_bits[0] ^= np.uint8(1)
    if truncate_certificate:
        outcome = next(
            row for row in working.decode.tiles.values()
            if row.state == "certified")
        outcome.user_bits = outcome.user_bits[:-1]
    working.validate_invariants()
    receiver.save_session(path, working)
    return working


def test_certificate_union_reports_provenance_overlap_and_crc_bound(
        base_state, tmp_path: Path) -> None:
    base_path, base = base_state
    alternate_path = tmp_path / "alternate.pkl"
    alternate = _variant(base, alternate_path, demote=True)
    sources = merge_e023b.load_sources([
        merge_e023b.SourceSpec("native", base_path.resolve()),
        merge_e023b.SourceSpec("decimated", alternate_path.resolve()),
    ])
    assert all(not hasattr(source, "session") for source in sources)
    assert all(
        isinstance(certificate.user_bits_packed, bytes)
        for source in sources
        for certificate in source.certificates.values()
    )
    payload = merge_e023b.build_union(sources)

    n_base = sum(row.state == "certified"
                 for row in base.decode.tiles.values())
    n_alternate = sum(row.state == "certified"
                      for row in alternate.decode.tiles.values())
    stats = payload["statistics"]
    assert stats["merged_certificates"] == n_base
    assert stats["shared_certificates"] == n_alternate
    assert stats["exclusive_certificates"] == 1
    assert stats["all_sources_certificates"] == n_alternate
    base_bp_iterations = sum(row.n_iters for row in base.attempts)
    alternate_bp_iterations = sum(row.n_iters for row in alternate.attempts)
    full_states = payloaddec.full_tile_states(base.decode)
    n_total = len(full_states)
    n_degenerate = sum(
        state == "degenerate" for state in full_states.values())
    assert stats["per_source"]["native"] == {
        "certified": n_base,
        "shared": n_alternate,
        "exclusive": 1,
        "certified_user_bits": sum(
            row.user_bits.size for row in base.decode.tiles.values()
            if row.state == "certified"),
        "bp_iterations": base_bp_iterations,
        "tiles": {
            "total": n_total,
            "degenerate": n_degenerate,
            "nondegenerate": n_total - n_degenerate,
            "unresolved_nondegenerate": (
                n_total - n_degenerate - n_base),
        },
    }
    assert stats["pairwise"] == [{
        "left": "native", "right": "decimated",
        "intersection": n_alternate, "left_only": 1,
        "right_only": 0, "union": n_base,
    }]
    total_calls = base.decode.n_attempts + alternate.decode.n_attempts
    assert stats["total_crc_calls"] == total_calls
    assert stats["total_bp_iterations"] == (
        base_bp_iterations + alternate_bp_iterations)
    assert stats["tiles"] == {
        "total": n_total,
        "degenerate": n_degenerate,
        "nondegenerate": n_total - n_degenerate,
        "unresolved_nondegenerate": (
            n_total - n_degenerate - n_base),
    }
    assert stats["conservative_crc_false_accept_bound"] == pytest.approx(
        total_calls * 2.0 ** -32)

    assert payload["compatibility"]["ordered_capture_ids"] == [
        scan.capture_id for scan in base.scans]
    assert len(payload["implementation"]["merge_script_sha256"]) == 64
    assert len(payload["implementation"]["receiver_sha256"]) == 64
    provenance = payload["provenance"]["sources"]
    assert [row["label"] for row in provenance] == ["native", "decimated"]
    assert provenance[0]["authoritative_sha256"] == (
        receiver.authoritative_digest(base))
    assert provenance[0]["state_file_sha256"] == hashlib.sha256(
        base_path.read_bytes()).hexdigest()
    assert provenance[0]["scans"][0]["capture_id"] == base.scans[0].capture_id
    assert provenance[0]["bp_iterations"] == base_bp_iterations

    first = payload["certificates"][0]
    restored = np.unpackbits(
        np.frombuffer(bytes.fromhex(first["user_bits_packed_hex"]),
                      dtype=np.uint8),
        bitorder=first["pack_bitorder"])[:first["n_user_bits"]]
    key = (first["page"], *first["tile_yx"])
    assert np.array_equal(restored, base.decode.tiles[key].user_bits)
    attempt = first["sources"][0]["attempt"]
    expected_attempt = next(
        row for row in base.attempts
        if row.certified_new
        and (row.page, *row.tile_yx) == key)
    assert attempt["attempt_id"] == expected_attempt.attempt_id
    assert attempt["evidence_digest"] == expected_attempt.evidence_digest
    assert attempt["decoder_profile"] == expected_attempt.decoder_profile
    assert attempt["scan_ids"] == list(expected_attempt.scan_ids)
    assert attempt["capture_ids"] == list(expected_attempt.capture_ids)

    out = tmp_path / "union.json"
    merge_e023b.write_json_atomic(
        out, payload, source_paths=tuple(source.path for source in sources))
    assert json.loads(out.read_text()) == payload


def test_union_accepts_differing_dpi_for_aligned_correlated_views(
        base_state, tmp_path: Path) -> None:
    base_path, base = base_state
    native_path = tmp_path / "native-4800.pkl"
    _variant(base, native_path, dpi=4800.0)
    sources = merge_e023b.load_sources([
        merge_e023b.SourceSpec("decimated", base_path.resolve()),
        merge_e023b.SourceSpec("native", native_path.resolve()),
    ])

    payload = merge_e023b.build_union(sources)

    assert [row["dpi"] for row in payload["provenance"]["sources"]] == [
        1600.0, 4800.0]
    assert "dpi" not in payload["compatibility"]
    assert payload["compatibility"]["ordered_capture_ids"] == [
        scan.capture_id for scan in base.scans]

    incompatible = list(sources)
    incompatible[1] = replace(
        incompatible[1],
        compatibility_key=(
            *incompatible[1].compatibility_key[:-1],
            "different-rate",
        ),
    )
    with pytest.raises(
            ValueError, match="format/seed/geometry/pages/rate differ"):
        merge_e023b.build_union(incompatible)


def test_union_rejects_duplicate_semantic_state_and_source_syntax(
        base_state, tmp_path: Path) -> None:
    base_path, base = base_state
    duplicate = tmp_path / "duplicate.pkl"
    shutil.copyfile(base_path, duplicate)
    with pytest.raises(ValueError, match="same authoritative digest"):
        merge_e023b.load_sources([
            merge_e023b.SourceSpec("one", base_path.resolve()),
            merge_e023b.SourceSpec("two", duplicate.resolve()),
        ])
    with pytest.raises(ValueError, match="duplicate source label"):
        merge_e023b.load_sources([
            merge_e023b.SourceSpec("same", base_path.resolve()),
            merge_e023b.SourceSpec("same", duplicate.resolve()),
        ])
    with pytest.raises(ValueError, match="expected LABEL=STATE"):
        merge_e023b.parse_source(str(base_path))
    with pytest.raises(ValueError, match="invalid source label"):
        merge_e023b.parse_source(f"bad label={base_path}")

    fatal_path = tmp_path / "fatal.pkl"
    fatal = base.fork()
    fatal.decode.fatal.append("injected fatal integrity record")
    receiver.save_session(fatal_path, fatal)
    with pytest.raises(ValueError, match="fatal integrity records"):
        merge_e023b.load_sources([
            merge_e023b.SourceSpec("fatal", fatal_path.resolve()),
            merge_e023b.SourceSpec("base", base_path.resolve()),
        ])


def test_union_rejects_capture_mismatch_and_bit_conflict(
        base_state, tmp_path: Path) -> None:
    base_path, base = base_state
    wrong_capture_path = tmp_path / "wrong-capture.pkl"
    _variant(base, wrong_capture_path, capture_id="different-physical-scan")
    wrong_capture_sources = merge_e023b.load_sources([
        merge_e023b.SourceSpec("native", base_path.resolve()),
        merge_e023b.SourceSpec("wrong", wrong_capture_path.resolve()),
    ])
    with pytest.raises(ValueError, match="same ordered capture IDs"):
        merge_e023b.build_union(wrong_capture_sources)

    conflict_path = tmp_path / "conflict.pkl"
    _variant(base, conflict_path, flip_certificate=True)
    conflict_sources = merge_e023b.load_sources([
        merge_e023b.SourceSpec("native", base_path.resolve()),
        merge_e023b.SourceSpec("conflict", conflict_path.resolve()),
    ])
    with pytest.raises(ValueError, match="conflicting certified user bits"):
        merge_e023b.build_union(conflict_sources)

    wrong_length_path = tmp_path / "wrong-length.pkl"
    _variant(base, wrong_length_path, truncate_certificate=True)
    with pytest.raises(ValueError, match="certified bits.*expected"):
        merge_e023b.load_sources([
            merge_e023b.SourceSpec("native", base_path.resolve()),
            merge_e023b.SourceSpec(
                "wrong-length", wrong_length_path.resolve()),
        ])


def test_atomic_output_failure_preserves_previous_file(
        tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "union.json"
    target.write_text("previous\n")

    def fail_replace(_source, _target):
        raise OSError("injected replace failure")

    monkeypatch.setattr(merge_e023b.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        merge_e023b.write_json_atomic(target, {"new": True})
    assert target.read_text() == "previous\n"
    assert list(tmp_path.glob(".union.json.*.tmp")) == []
    with pytest.raises(ValueError, match="must not overwrite"):
        merge_e023b.write_json_atomic(
            target, {"new": True}, source_paths=(target.resolve(),))


def test_cli_reports_malformed_pickle_without_traceback(
        base_state, tmp_path: Path, monkeypatch, capsys) -> None:
    base_path, _base = base_state
    malformed = tmp_path / "malformed.pkl"
    malformed.write_bytes(b"not-a-pickle")
    monkeypatch.setattr(sys, "argv", [
        "merge_e023b.py",
        "--source", f"bad={malformed}",
        "--source", f"base={base_path}",
        "--out", str(tmp_path / "out.json"),
    ])
    with pytest.raises(SystemExit) as raised:
        merge_e023b.main()
    assert raised.value.code == 2
    error = capsys.readouterr().err
    assert "error:" in error
    assert "Traceback" not in error


def test_load_rejects_state_changed_during_deserialization(
        base_state, tmp_path: Path, monkeypatch) -> None:
    base_path, _base = base_state
    changing = tmp_path / "changing.pkl"
    shutil.copyfile(base_path, changing)
    original_load = merge_e023b.pickle.load
    changed = False

    def mutate_after_load(stream):
        nonlocal changed
        payload = original_load(stream)
        if not changed:
            changed = True
            with changing.open("ab") as writer:
                writer.write(b"changed")
        return payload

    monkeypatch.setattr(merge_e023b.pickle, "load", mutate_after_load)
    monkeypatch.setattr(
        merge_e023b, "_stat_signature", lambda _stat: (0,))
    with pytest.raises(ValueError, match="changed while reading"):
        merge_e023b.load_sources([
            merge_e023b.SourceSpec("changing", changing.resolve()),
            merge_e023b.SourceSpec("base", base_path.resolve()),
        ])


def test_tile_universe_disagreement_is_fail_closed(
        base_state, tmp_path: Path) -> None:
    base_path, base = base_state
    alternate_path = tmp_path / "alternate.pkl"
    _variant(base, alternate_path, demote=True)
    sources = merge_e023b.load_sources([
        merge_e023b.SourceSpec("native", base_path.resolve()),
        merge_e023b.SourceSpec("decimated", alternate_path.resolve()),
    ])
    changed_keys = set(sources[1].tile_keys)
    changed_keys.remove(next(iter(changed_keys)))
    sources[1] = replace(
        sources[1], tile_keys=frozenset(changed_keys))
    with pytest.raises(ValueError, match="different tile universe"):
        merge_e023b.build_union(sources)
