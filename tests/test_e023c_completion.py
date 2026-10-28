"""Manifest, symbol, rank, integrity, and stop-policy pins for E023c."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023c-scale-space-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

from paperholo import fountain  # noqa: E402
from paperholo.formats import FormatDescriptor  # noqa: E402
import completion  # noqa: E402


def _fixture(tmp_path: Path):
    descriptor = FormatDescriptor(
        "completion-test-v3-c3",
        b"paper-store/e023c-completion-test",
        3,
        "kcell-c3",
        (300, 300),
        ldpc_rate="r0550",
    )
    data = (b"e023c-scale-space-completion-" * 70)[:2000]
    assert len(data) == 2000
    volume = fountain.VolumeSpec(
        n_pages=1,
        data_len_bytes=len(data),
        seed=descriptor.seed,
        ldpc_rate_id="r0550",
        compose_spec=descriptor.spec(),
    )
    assert volume.k_total == 8 and volume.n_symbols_total == 16
    encoded = fountain.volume_encode(data, volume)
    framed = fountain.encode_volume_pages(data, volume)[0]
    page_user = np.asarray(encoded.page_user_bits[0], np.uint8)

    certificates = {}
    inert_key = None
    for row in framed["per_tile"]:
        tile_yx = tuple(int(value) for value in row["tile_yx"])
        offset = int(row["user_offset"])
        size = int(row["user_bits"])
        if size == 0:
            continue
        key = (0, *tile_yx)
        bits = page_user[offset:offset + size].copy()
        if fountain.esi_of_tile(volume, 0, tile_yx) is None:
            if inert_key is None:
                certificates[key] = bits
                inert_key = key
            continue
        certificates[key] = bits
    assert inert_key is not None

    digest = hashlib.sha256(data).hexdigest()
    manifest = {
        "profile": "completion-test-c3",
        "seed": descriptor.seed.decode("ascii"),
        "format": {
            "format_id": descriptor.format_id,
            "layout_version": descriptor.layout_version,
            "encoding_id": descriptor.encoding_id,
            "plane": descriptor.plane,
            "page_cells_yx": list(descriptor.page_cells_yx),
            "ldpc_rate_id": "r0550",
            "seed": descriptor.seed.decode("ascii"),
        },
        "payload": {
            "data_len_bytes": len(data),
            "data_sha256": digest,
        },
        "volume": {
            "fountain_version": fountain.FOUNTAIN_VERSION,
            "n_pages": 1,
            "data_len_bytes": len(data),
            "data_sha256": digest,
            "ldpc_rate_id": "r0550",
            "k_total": volume.k_total,
            "n_symbols_total": volume.n_symbols_total,
            "symbol_bits": volume.symbol_bits,
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return manifest_path, volume, certificates, inert_key, data


def _source_certificates(certificates, volume, count: int):
    selected = {}
    for key, bits in sorted(certificates.items()):
        esi = fountain.esi_of_tile(volume, key[0], key[1:])
        if esi is not None and esi[1] < count:
            selected[key] = bits.copy()
    assert len(selected) == count
    return selected


def test_verified_completion_uses_actual_fountain_decode_and_sha(
    tmp_path: Path,
) -> None:
    manifest_path, volume, certificates, _inert, data = _fixture(tmp_path)
    before = {key: value.copy() for key, value in certificates.items()}

    report, recovered = completion.evaluate(certificates, manifest_path)

    assert recovered == data
    assert report["status"] == "verified"
    assert report["payload"] == {
        "recovered": True,
        "verified": True,
        "actual_len_bytes": len(data),
        "actual_sha256": hashlib.sha256(data).hexdigest(),
        "length_matches": True,
        "sha256_matches": True,
    }
    assert report["fountain"]["rank"] == volume.k_total
    assert report["fountain"]["rank_shortfall"] == 0
    assert report["fountain"]["solved_all"]
    assert report["certificates"]["certified_fountain"] == 16
    assert report["certificates"]["certified_fountain_inert"] == 1
    assert completion.should_stop(report)
    assert not completion.should_stop(report, complete=True)
    assert all(np.array_equal(value, before[key])
               for key, value in certificates.items())


def test_under_ranked_report_is_open_even_near_k(tmp_path: Path) -> None:
    manifest_path, volume, certificates, _inert, _data = _fixture(tmp_path)
    under = _source_certificates(
        certificates, volume, volume.k_total - 1)

    first, recovered = completion.evaluate(under, manifest_path)
    second = completion.completion_report(under, manifest_path)

    assert recovered is None
    assert first == second
    assert json.loads(json.dumps(first, sort_keys=True)) == first
    assert first["status"] == "open"
    assert not first["payload"]["recovered"]
    assert first["payload"]["actual_len_bytes"] is None
    assert first["payload"]["actual_sha256"] is None
    assert first["payload"]["verified"] is False
    assert first["fountain"]["rank"] == volume.k_total - 1
    assert first["fountain"]["rank_shortfall"] == 1
    assert not completion.should_stop(first)


def test_solved_but_wrong_payload_is_integrity_failure_not_stop(
    tmp_path: Path,
) -> None:
    manifest_path, volume, certificates, _inert, data = _fixture(tmp_path)
    corrupt = {key: value.copy() for key, value in certificates.items()}
    source = _source_certificates(corrupt, volume, volume.k_total)
    first_key = sorted(source)[0]
    corrupt[first_key][0] ^= np.uint8(1)

    report, recovered = completion.evaluate(corrupt, manifest_path)

    assert recovered is not None and recovered != data
    assert report["status"] == "integrity_failure"
    assert report["payload"]["recovered"]
    assert report["payload"]["length_matches"]
    assert not report["payload"]["sha256_matches"]
    assert not report["payload"]["verified"]
    assert report["fountain"]["rank_shortfall"] == 0
    assert not completion.should_stop(report)


@pytest.mark.parametrize("delta", [-1, 1])
def test_every_certificate_has_exact_manifest_user_bit_length(
    tmp_path: Path,
    delta: int,
) -> None:
    manifest_path, _volume, certificates, inert_key, _data = _fixture(
        tmp_path)
    malformed = {key: value.copy() for key, value in certificates.items()}
    key = inert_key if delta == 1 else next(
        key for key in sorted(malformed) if key != inert_key)
    if delta < 0:
        malformed[key] = malformed[key][:-1]
    else:
        malformed[key] = np.append(malformed[key], np.uint8(0))
    with pytest.raises(ValueError, match=r"user bits; expected"):
        completion.evaluate(malformed, manifest_path)


def test_malformed_keys_and_nonbinary_bits_are_fatal(tmp_path: Path) -> None:
    manifest_path, _volume, certificates, _inert, _data = _fixture(tmp_path)
    key = sorted(certificates)[0]
    bits = certificates[key]
    with pytest.raises(ValueError, match=r"must be \(page, tile_y, tile_x\)"):
        completion.evaluate({key[:2]: bits}, manifest_path)
    with pytest.raises(ValueError, match="component 0 must be an integer"):
        completion.evaluate({("0", key[1], key[2]): bits}, manifest_path)
    with pytest.raises(ValueError, match="outside the volume"):
        completion.evaluate({(1, key[1], key[2]): bits}, manifest_path)
    with pytest.raises(ValueError, match="outside the page"):
        completion.evaluate({(0, 999, 999): bits}, manifest_path)
    bad = bits.copy()
    bad[0] = 2
    with pytest.raises(ValueError, match="not binary"):
        completion.evaluate({key: bad}, manifest_path)


def test_manifest_loader_keeps_e018b_validation_strict(tmp_path: Path) -> None:
    manifest_path, _volume, _certificates, _inert, _data = _fixture(tmp_path)
    manifest = completion.load_manifest(manifest_path)
    assert manifest.file_sha256 == hashlib.sha256(
        manifest_path.read_bytes()).hexdigest()
    raw = json.loads(manifest_path.read_text())
    raw["volume"]["symbol_bits"] += 1
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="symbol_bits mismatch"):
        completion.load_manifest(manifest_path)


def test_stop_policy_rejects_truthy_or_malformed_verification() -> None:
    with pytest.raises(TypeError, match="complete must be boolean"):
        completion.should_stop(
            {"payload": {"verified": True}}, complete=1)
    with pytest.raises(ValueError, match="no payload"):
        completion.should_stop({})
    with pytest.raises(ValueError, match="must be boolean"):
        completion.should_stop({"payload": {"verified": "yes"}})
