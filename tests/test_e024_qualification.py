"""Qualification-harness contracts for E024."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/024-feedback-receiver"
E023C = ROOT / "experiments/023c-scale-space-receiver"
HP_E018B_REPORT = EXP / "HP-E018B-QUALIFICATION.json"
HP_E018B_REPORT_SHA256 = (
    "6b48f7baceecec23db9a854c6aa04c3dd00ac66f849e6cbdbe683f37b51ae5c9")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

import qualify_e024  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _footing(
    *,
    scan_id: str = "s000",
    dpi: float = 1600.0,
    source_path: str = "decimated.tiff",
):
    envelope = SimpleNamespace(
        algorithm_id="e023b.1-algorithm-arms",
        format_id="e018-v3-c3",
        seed=b"same-printed-volume",
        cell_dots=3,
        page_cells_yx=(2220, 1500),
        pages=(0,),
        rate_id="r0550",
        evidence_policy="one-owner-per-scan/independent-capture/v1",
        detector_profile="ctx-pava-v1",
        search_config_sha256="a" * 64,
        dpi=dpi,
    )
    scans = [
        SimpleNamespace(
            scan_id=scan_id, capture_id="physical-capture-1",
            source_path=source_path, source_sha256="b" * 64,
            source_size=123, image_shape=(10, 20), image_dtype="uint8"),
    ]
    return SimpleNamespace(envelope=envelope, scans=scans)


def test_cross_footing_identity_excludes_rasterization_details() -> None:
    decimated = qualify_e024._footing_compatibility(_footing())
    native = qualify_e024._footing_compatibility(_footing(
        scan_id="native-local-id", dpi=4800.0,
        source_path="native.tiff"))

    assert decimated == native
    result = qualify_e024._validate_footing_compatibility([
        ("decimated", decimated), ("native", native)])
    assert result["compatible"]
    assert result["compared_labels"] == ["decimated", "native"]


@pytest.mark.parametrize(
    "field",
    [
        "algorithm_id", "format_id", "seed_hex", "cell_dots",
        "page_cells_yx", "pages", "rate_id", "evidence_policy",
        "detector_profile", "search_config_sha256",
        "ordered_capture_ids",
    ],
)
def test_cross_footing_identity_rejects_every_control_field(
    field: str,
) -> None:
    reference = qualify_e024._footing_compatibility(_footing())
    changed = copy.deepcopy(reference)
    if isinstance(changed[field], list):
        changed[field] = [*changed[field], "different"]
    elif isinstance(changed[field], int):
        changed[field] += 1
    else:
        changed[field] = str(changed[field]) + "-different"

    with pytest.raises(ValueError, match=field):
        qualify_e024._validate_footing_compatibility([
            ("decimated", reference), ("native", changed)])


def test_certificate_portfolio_reports_exclusive_and_conflicting_views() -> None:
    a = (8, b"\x01")
    b = (8, b"\x02")
    clean = qualify_e024._certificate_portfolio({
        "decimated": {(0, 0, 0): a, (0, 0, 1): b},
        "native": {(0, 0, 0): a, (0, 1, 0): b},
    })
    assert clean["conflict_free"]
    assert clean["union"]["count"] == 3
    assert clean["intersection_count"] == 1
    assert clean["exclusive_count"] == 2

    conflict = qualify_e024._certificate_portfolio({
        "decimated": {(0, 0, 0): a},
        "native": {(0, 0, 0): b},
    })
    assert not conflict["conflict_free"]
    assert conflict["conflict_count"] == 1
    assert conflict["union"] is None


def test_qualification_requires_two_distinct_paths() -> None:
    with pytest.raises(ValueError, match="at least two"):
        qualify_e024._parse_baselines(["decimated=/tmp/one.pkl"])
    with pytest.raises(ValueError, match="duplicate baseline state path"):
        qualify_e024._parse_baselines([
            "decimated=/tmp/same.pkl",
            "native=/tmp/same.pkl",
        ])


def test_qualification_requires_distinct_artifact_and_state_identities() -> None:
    first = {
        "file_sha256": "a" * 64,
        "file_size": 10,
        "authoritative_sha256": "b" * 64,
    }
    second = {
        "file_sha256": "c" * 64,
        "file_size": 20,
        "authoritative_sha256": "d" * 64,
    }
    result = qualify_e024._validate_distinct_footing_identities([
        ("decimated", first), ("native", second)])
    assert result["distinct"]

    with pytest.raises(ValueError, match="baseline artifact"):
        qualify_e024._validate_distinct_footing_identities([
            ("decimated", first), ("native", dict(first))])
    duplicate_state = dict(second)
    duplicate_state["authoritative_sha256"] = (
        first["authoritative_sha256"])
    with pytest.raises(ValueError, match="authoritative state"):
        qualify_e024._validate_distinct_footing_identities([
            ("decimated", first), ("native", duplicate_state)])


def test_union_qualification_prebinds_every_footing() -> None:
    preflight = {
        "identities": {
            "file_identities": [
                {
                    "label": "decimated",
                    "file_sha256": "a" * 64,
                    "file_size": 10,
                    "authoritative_sha256": "b" * 64,
                },
                {
                    "label": "native",
                    "file_sha256": "c" * 64,
                    "file_size": 20,
                    "authoritative_sha256": "d" * 64,
                },
            ],
        },
    }
    proof = {
        "sources": [
            {
                "label": "dec-source",
                "state_file_sha256": "a" * 64,
                "state_file_size": 10,
                "authoritative_sha256": "b" * 64,
            },
            {
                "label": "native-source",
                "state_file_sha256": "c" * 64,
                "state_file_size": 20,
                "authoritative_sha256": "d" * 64,
            },
        ],
    }
    result = qualify_e024._validate_union_footing_bindings(
        proof, preflight)
    assert result["all_footings_bound"]
    assert result["bindings"] == [
        {"footing": "decimated", "union_source": "dec-source"},
        {"footing": "native", "union_source": "native-source"},
    ]

    mismatched = copy.deepcopy(preflight)
    mismatched["identities"]["file_identities"][1][
        "authoritative_sha256"] = "e" * 64
    with pytest.raises(ValueError, match="not an exact source artifact"):
        qualify_e024._validate_union_footing_bindings(
            proof, mismatched)


def test_hp_e018b_retention_record_is_self_consistent_and_pinned() -> None:
    assert _sha256(HP_E018B_REPORT) == HP_E018B_REPORT_SHA256
    report = json.loads(HP_E018B_REPORT.read_text())
    assert report["magic"] == "e024-hp-e018b-retention-v1"
    assert report["boundary"]["recovery_uses_ground_truth"] is False
    assert "no fountain-derived E024 stop condition" in (
        report["boundary"]["fountain_use"])
    assert "little-bitorder" in report["digest_conventions"][
        "certificate_bits_sha256"]

    for key in ("bridge_at_run", "bridge_current"):
        bridge = report["implementation"][key]
        assert _sha256(ROOT / bridge["path"]) == bridge["sha256"]
    observer = report["implementation"]["post_run_observer_instrumentation"]
    assert observer["commit"] == (
        "5ee753a9b3b330c6e8201b823153135075ec137c")
    assert observer["fresh_blind_requalification"] is False
    assert observer["changed_fingerprint_keys"] == [
        "e023c:cascade", "e023c:run", "lower:paperholo.pilotsearch"]
    for profile, filename in (
        ("c3", "E023C-CASCADE-HP1200.json"),
        ("c2", "E023C-CASCADE-HP1200-C2.json"),
    ):
        pin = report["source_artifacts"][
            f"tracked_{profile}_qualification"]
        assert pin["scope_profile"] == profile
        assert _sha256(E023C / filename) == pin["sha256"]
        e023c_report = json.loads((E023C / filename).read_text())
        measured = report["results"][
            "production_e023c_then_per_lane_e024_refine"][profile]
        assert measured["generation_zero"][
            "certificate_set_sha256"] == e023c_report["portfolio"][
                "certificate_set_sha256"]

    assert report["captures"]["c3"]["manifest_path_at_run"] == (
        "experiments/018b-payload-sheet/build/"
        "e018b-c3-012d9e3ae693_manifest.json")
    assert report["captures"]["c2"]["ground_truth_path_at_run"] == (
        "experiments/018b-payload-sheet/build/"
        "e018b-c2-424e41a28257_gt/"
        "K__e018b_c2_424e41a28257_field.npy")

    assert all(
        row["gates_ok"]
        for row in report["source_artifacts"]["ignored_audits"].values()
    )
    bound = report["source_artifacts"]["bound_v2_reaudits"]
    assert {
        profile: (row["status"], row["gates_ok"], row["audit_sha256"])
        for profile, row in bound.items()
    } == {
        "e023c_c3_e024": (
            "QUALIFIED_BOUND", True,
            "2b70cdaabe5c60f4a2ffee75b77d4abe980a3e4bacd1880659f4a733694375a4"),
        "e023c_c2_e024": (
            "QUALIFIED_BOUND", True,
            "8f54ac717cf661bbb227f6e169b9f818357fa70b918ca89f05dd15d51e3511f2"),
    }
    for experiment in report["results"].values():
        for row in experiment.values():
            generation_zero = row["generation_zero"]
            final = row["final"]
            new = row["new"]
            assert generation_zero["ldpc_certificates"] == (
                generation_zero["useful_symbols"]
                + generation_zero["inert_certificates"])
            assert final["ldpc_certificates"] == (
                final["useful_symbols"] + final["inert_certificates"])
            assert final["ldpc_certificates"] == (
                generation_zero["ldpc_certificates"]
                + new["ldpc_certificates"])
            assert new["ldpc_certificates"] == (
                new["useful_symbols"] + new["inert_certificates"])
            assert row["safety"] == {
                "gates_ok": True,
                "wrong_certificates": 0,
                "conflicts": 0,
                "lost_certificates": 0,
                "changed_generation_zero_values": 0,
            }

    assert report["results"]["standalone_e023b_then_e024_refine"][
        "c3"]["work"]["refused_revisions"] == 100
    assert report["results"][
        "production_e023c_then_per_lane_e024_refine"][
            "c2"]["work_across_all_lanes"]["refused_revisions"] == 624
