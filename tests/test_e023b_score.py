"""Manifest, rank, and integrity contracts for the E023b volume scorer."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023b-integrated-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

from paperholo import fountain, ldpc, payloaddec  # noqa: E402
from paperholo.formats import FormatDescriptor  # noqa: E402
import score_e023b  # noqa: E402


def _fixture(tmp_path: Path, *, certify: str = "all"):
    descriptor = FormatDescriptor(
        "score-test-v3-c3",
        b"paper-store/e023b-score-test",
        3,
        "kcell-c3",
        (600, 480),
        ldpc_rate="r0550",
    )
    data = (b"e023b-score-payload-" * 211) + b"\0"
    vspec = fountain.VolumeSpec(
        n_pages=1,
        data_len_bytes=len(data),
        seed=descriptor.seed,
        ldpc_rate_id="r0550",
        compose_spec=descriptor.spec(),
    )
    encoded = fountain.volume_encode(data, vspec)
    framed = fountain.encode_volume_pages(data, vspec)[0]
    page_user = np.asarray(encoded.page_user_bits[0], np.uint8)

    tiles = {}
    interior_rows = []
    for row in framed["per_tile"]:
        tile_yx = tuple(row["tile_yx"])
        if fountain.esi_of_tile(vspec, 0, tile_yx) is None:
            continue
        interior_rows.append(row)
    selected = (
        interior_rows
        if certify == "all"
        else interior_rows[:max(0, vspec.k_total - 1)]
    )
    for row in selected:
        tile_yx = tuple(row["tile_yx"])
        offset = int(row["user_offset"])
        size = int(row["user_bits"])
        tiles[(0, *tile_yx)] = payloaddec.TileOutcome(
            page=0,
            tile_yx=tile_yx,
            state="certified",
            user_bits=page_user[offset:offset + size].copy(),
            certified_by="fixture",
        )
    inert = next(
        row for row in framed["per_tile"]
        if fountain.esi_of_tile(vspec, 0, tuple(row["tile_yx"])) is None
        and int(row["user_bits"]) > 0
    )
    inert_yx = tuple(inert["tile_yx"])
    inert_offset = int(inert["user_offset"])
    inert_size = int(inert["user_bits"])
    tiles[(0, *inert_yx)] = payloaddec.TileOutcome(
        page=0,
        tile_yx=inert_yx,
        state="certified",
        user_bits=page_user[
            inert_offset:inert_offset + inert_size
        ].copy(),
        certified_by="fixture",
    )

    state_path = tmp_path / "state.pkl"
    state_path.write_bytes(b"fixture-state")
    envelope = SimpleNamespace(
        format_id=descriptor.format_id,
        seed=descriptor.seed,
        cell_dots=descriptor.cell_dots,
        page_cells_yx=descriptor.page_cells_yx,
        pages=(0,),
        dpi=1600.0,
        rate_id="r0550",
        detector_profile="ctx-pava-v1",
    )
    decode = SimpleNamespace(
        tiles=tiles,
        fatal=[],
        n_attempts=len(tiles),
    )
    session = SimpleNamespace(
        envelope=envelope,
        decode=decode,
        attempts=[],
        scans=[],
    )
    manifest = {
        "profile": "test-c3",
        "seed": descriptor.seed.decode(),
        "format": {
            "format_id": descriptor.format_id,
            "layout_version": descriptor.layout_version,
            "encoding_id": descriptor.encoding_id,
            "plane": descriptor.plane,
            "page_cells_yx": list(descriptor.page_cells_yx),
            "ldpc_rate_id": "r0550",
            "seed": descriptor.seed.decode(),
        },
        "payload": {
            "data_len_bytes": len(data),
            "data_sha256": hashlib.sha256(data).hexdigest(),
        },
        "volume": {
            "fountain_version": fountain.FOUNTAIN_VERSION,
            "n_pages": 1,
            "data_len_bytes": len(data),
            "data_sha256": hashlib.sha256(data).hexdigest(),
            "ldpc_rate_id": "r0550",
            "k_total": vspec.k_total,
            "n_symbols_total": vspec.n_symbols_total,
            "symbol_bits": vspec.symbol_bits,
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return session, state_path, manifest_path, data


def test_full_certificate_set_recovers_and_verifies_payload(
        tmp_path: Path) -> None:
    session, state_path, manifest_path, data = _fixture(tmp_path)
    manifest = score_e023b.load_manifest(manifest_path)

    report, recovered = score_e023b.score_session(
        session, manifest, state_path=state_path, label="full")

    assert recovered == data
    assert report["payload"]["verified"]
    assert report["payload"]["sha256_matches"]
    assert report["fountain"]["rank"] == report[
        "fountain"]["source_symbols_needed"]
    assert report["fountain"]["rank_shortfall"] == 0
    assert report["tiles"]["certified_fountain"] == (
        manifest.volume.n_symbols_total)
    assert report["tiles"]["certified_ldpc"] == (
        manifest.volume.n_symbols_total + 1)
    assert report["tiles"]["certified_fountain_inert"] == 1


def test_under_ranked_state_is_an_honest_open_score(tmp_path: Path) -> None:
    session, state_path, manifest_path, _data = _fixture(
        tmp_path, certify="under")
    manifest = score_e023b.load_manifest(manifest_path)

    report, recovered = score_e023b.score_session(
        session, manifest, state_path=state_path, label="open")

    assert recovered is None
    assert not report["payload"]["recovered"]
    assert report["payload"]["sha256_matches"] is None
    assert report["fountain"]["rank_shortfall"] > 0
    assert report["fountain"]["rank"] < report[
        "fountain"]["source_symbols_needed"]


def test_final_hash_detects_a_wrong_certified_symbol(tmp_path: Path) -> None:
    session, state_path, manifest_path, data = _fixture(tmp_path)
    outcome = next(iter(session.decode.tiles.values()))
    outcome.user_bits[0] ^= np.uint8(1)
    manifest = score_e023b.load_manifest(manifest_path)

    report, recovered = score_e023b.score_session(
        session, manifest, state_path=state_path, label="corrupt")

    assert recovered is not None and recovered != data
    assert report["payload"]["recovered"]
    assert not report["payload"]["verified"]
    assert not report["payload"]["sha256_matches"]


def test_manifest_and_state_identity_mismatches_are_refused(
        tmp_path: Path) -> None:
    session, state_path, manifest_path, _data = _fixture(tmp_path)
    manifest = score_e023b.load_manifest(manifest_path)
    session.envelope.format_id = "different-format"
    with pytest.raises(ValueError, match="state/manifest format mismatch"):
        score_e023b.score_session(
            session, manifest, state_path=state_path, label="bad")

    raw = json.loads(manifest_path.read_text())
    raw["volume"]["symbol_bits"] += 1
    manifest_path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="symbol_bits mismatch"):
        score_e023b.load_manifest(manifest_path)


def test_json_and_recovered_writes_are_atomic(tmp_path: Path) -> None:
    report_path = tmp_path / "score.json"
    recovered_path = tmp_path / "payload.bin"
    score_e023b.write_json_atomic(report_path, {"score": 1})
    score_e023b.write_bytes_atomic(recovered_path, b"payload")
    assert json.loads(report_path.read_text()) == {"score": 1}
    assert recovered_path.read_bytes() == b"payload"
    assert not list(tmp_path.glob("*.tmp"))


def test_output_paths_cannot_overwrite_inputs(tmp_path: Path) -> None:
    state = tmp_path / "state.pkl"
    manifest = tmp_path / "manifest.json"
    with pytest.raises(ValueError, match="must not overwrite"):
        score_e023b.validate_output_paths(
            state, manifest, report=state, recovered=None)
    with pytest.raises(ValueError, match="different files"):
        score_e023b.validate_output_paths(
            state, manifest,
            report=tmp_path / "same.bin",
            recovered=tmp_path / "same.bin")
