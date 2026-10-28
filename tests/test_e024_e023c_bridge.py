"""Contracts for exporting production E023c lanes into independent E024 runs."""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
E023B = ROOT / "experiments/023b-integrated-receiver"
E023C = ROOT / "experiments/023c-scale-space-receiver"
E024 = ROOT / "experiments/024-feedback-receiver"
for path in (ROOT / "src", E023B, E023C, E024):
    sys.path.insert(0, str(path))

import e023c_e024_bridge as bridge  # noqa: E402
import merge_e023b  # noqa: E402
import run_e023c  # noqa: E402
import test_e023b_session as session_test  # noqa: E402
from paperholo import compose, feedback, feedbackstate, receiver  # noqa: E402


class _CascadeFixture:
    def __init__(
        self, envelope, decoder_lanes, lane_sessions, capture_ids,
        certificate_union,
    ):
        self.envelope = envelope
        self.decoder_lanes = decoder_lanes
        self.lane_sessions = lane_sessions
        self.capture_ids = capture_ids
        self.certificate_union = certificate_union
        self.status = "exhausted"
        self.validated = False

    def validate_invariants(self) -> None:
        self.validated = True


def _receiver_lanes(tmp_path: Path):
    descriptor, upstream, image, _user, framed = session_test._fixture(
        tmp_path)
    coarse = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    coarse, _ = receiver.apply_scan(
        coarse, session_test._record(
            descriptor, upstream.scans[0], image))

    native = coarse.fork()
    native.envelope = replace(native.envelope, dpi=4800.0)
    native.scans = [replace(scan, dpi=4800.0) for scan in native.scans]
    native.validate_invariants()
    return descriptor, framed, coarse, native


def _cascade(coarse, native) -> _CascadeFixture:
    scales = (
        SimpleNamespace(
            level_id="coarse", ordinal=0, target_ppc=2.0,
            effective_dpi=1600.0),
        SimpleNamespace(
            level_id="native", ordinal=1, target_ppc=6.0,
            effective_dpi=4800.0),
    )
    implementation = (
        *run_e023c.implementation_fingerprints(),
        ("run_policy", "f" * 64),
    )
    envelope = SimpleNamespace(
        implementation_sha256=implementation,
        scale_plan=scales,
        format_id=coarse.envelope.format_id,
        pages=(0,),
    )
    coarse_meta = SimpleNamespace(
        lane_id="coarse-lane", level_id="coarse", lane_kind="primary",
        session_sha256=bridge.cascade_state.semantic_digest(coarse))
    native_meta = SimpleNamespace(
        lane_id="native-lane", level_id="native", lane_kind="primary",
        session_sha256=bridge.cascade_state.semantic_digest(native))
    certificate_union = {
        tuple(map(int, key)): SimpleNamespace(
            user_bits=(lambda bits=np.asarray(outcome.user_bits, np.uint8).copy():
                       bits.copy()))
        for key, outcome in coarse.decode.tiles.items()
        if outcome.state == "certified"
    }
    # Reverse insertion order so the exporter has to honor scale ordinals.
    return _CascadeFixture(
        envelope,
        {"native-lane": native_meta, "coarse-lane": coarse_meta},
        {"native-lane": native, "coarse-lane": coarse},
        tuple(scan.capture_id for scan in coarse.scans),
        certificate_union,
    )


def _export(
    tmp_path: Path,
    monkeypatch,
):
    descriptor, framed, coarse, native = _receiver_lanes(tmp_path)
    cascade = _cascade(coarse, native)
    source = tmp_path / "cascade.pkl"
    source.write_bytes(b"authenticated-cascade-fixture")
    out_dir = tmp_path / "lanes"
    monkeypatch.setattr(
        bridge.cascade_state, "load_session", lambda _path: cascade)
    monkeypatch.setattr(
        bridge.cascade_state, "authoritative_digest",
        lambda _session: "c" * 64)

    args = SimpleNamespace(
        cascade=source, out_dir=out_dir, manifest_out=None)
    assert bridge.command_export(args) == 0
    assert cascade.validated
    return descriptor, framed, coarse, native, cascade, args, out_dir


def test_export_is_causal_and_feeds_only_certificates_to_official_merge(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (_descriptor, _framed, coarse, _native, _cascade_state, args,
     out_dir) = _export(tmp_path, monkeypatch)
    manifest = json.loads((out_dir / "lanes.json").read_text())

    assert manifest["magic"] == bridge.EXPORT_MAGIC
    assert manifest["version"] == bridge.VERSION
    assert [row["level_id"] for row in manifest["lanes"]] == [
        "coarse", "native"]
    assert [row["label"] for row in manifest["lanes"]] == [
        "l00-coarse-primary-coarse-lane",
        "l01-native-primary-native-lane",
    ]
    assert len({row["path"] for row in manifest["lanes"]}) == 2
    assert all(row["lane_id"] in Path(row["path"]).name
               for row in manifest["lanes"])
    assert manifest["cascade"]["run_policy_sha256"] == "f" * 64
    assert manifest["cascade"]["authoritative_sha256"] == "c" * 64
    assert all(
        row["capture_ids"] == [scan.capture_id for scan in coarse.scans]
        for row in manifest["lanes"])

    source_specs = [
        merge_e023b.SourceSpec(row["label"], Path(row["path"]))
        for row in manifest["lanes"]
    ]
    sources = merge_e023b.load_sources(source_specs)
    union = merge_e023b.build_union(sources)
    assert union["magic"] == merge_e023b.UNION_MAGIC
    assert union["statistics"]["merged_certificates"] == (
        manifest["lanes"][0]["certified"])
    assert union["statistics"]["exclusive_certificates"] == 0
    assert union["compatibility"]["ordered_capture_ids"] == [
        scan.capture_id for scan in coarse.scans]
    assert [row["dpi"] for row in union["provenance"]["sources"]] == [
        1600.0, 4800.0]

    with pytest.raises(ValueError, match="refuses to overwrite"):
        bridge.command_export(args)


def _legacy_v1_manifest(current: dict, tmp_path: Path) -> tuple[Path, dict]:
    payload = json.loads(json.dumps(current))
    payload["magic"] = bridge.LEGACY_EXPORT_MAGIC
    payload["version"] = bridge.LEGACY_EXPORT_VERSION
    payload["tool_sha256"] = bridge.LEGACY_BRIDGE_SHA256
    legacy_dir = tmp_path / "legacy-v1-lanes"
    legacy_dir.mkdir()
    for row in payload["lanes"]:
        level = row["level_id"]
        label = f"l{row['ordinal']:02d}-{level}"
        target = legacy_dir / f"lane-{row['ordinal']:02d}-{level}.pkl"
        target.write_bytes(Path(row["path"]).read_bytes())
        file_sha, file_size = bridge._file_identity(target)
        row.update({
            "label": label,
            "path": str(target),
            "merge_source": f"{label}={target}",
            "state_file_sha256": file_sha,
            "state_file_size": file_size,
        })
    path = legacy_dir / "lanes-v1.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path, payload


def _adoption_fixture(tmp_path: Path, monkeypatch):
    exported = _export(tmp_path, monkeypatch)
    current = json.loads((exported[-1] / "lanes.json").read_text())
    legacy_path, legacy = _legacy_v1_manifest(current, tmp_path)
    output = tmp_path / "adopted-v2.json"
    args = SimpleNamespace(
        cascade=exported[-2].cascade,
        legacy_manifest=legacy_path,
        manifest_out=output,
    )
    return exported, legacy_path, legacy, output, args


def test_adopt_v1_binds_exact_legacy_files_without_rewriting_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (_exported, legacy_path, legacy, output,
     args) = _adoption_fixture(tmp_path, monkeypatch)
    identities_before = {
        row["lane_id"]: bridge._file_identity(Path(row["path"]))
        for row in legacy["lanes"]
    }

    assert bridge.command_adopt_v1(args) == 0
    adopted = json.loads(output.read_text())

    assert adopted["magic"] == bridge.EXPORT_MAGIC
    assert adopted["version"] == bridge.VERSION
    assert adopted["tool_sha256"] == bridge._file_identity(
        Path(bridge.__file__).resolve())[0]
    assert adopted["adoption"]["mode"] == (
        "frozen_v1_exact_artifact_adoption")
    assert adopted["adoption"]["state_files_rewritten"] is False
    assert adopted["adoption"]["legacy_manifest"] == {
        "path": str(legacy_path),
        "sha256": bridge._file_identity(legacy_path)[0],
        "file_size": bridge._file_identity(legacy_path)[1],
    }
    legacy_by_lane = {row["lane_id"]: row for row in legacy["lanes"]}
    assert [row["label"] for row in adopted["lanes"]] == [
        "l00-coarse-primary-coarse-lane",
        "l01-native-primary-native-lane",
    ]
    for row in adopted["lanes"]:
        old = legacy_by_lane[row["lane_id"]]
        assert row["path"] == old["path"]
        assert row["state_file_sha256"] == old["state_file_sha256"]
        assert row["state_file_size"] == old["state_file_size"]
        assert bridge._file_identity(Path(row["path"])) == (
            row["state_file_sha256"], row["state_file_size"])
    assert identities_before == {
        row["lane_id"]: bridge._file_identity(Path(row["path"]))
        for row in legacy["lanes"]
    }

    raw, identity = bridge._stable_bytes(output)
    validated, lanes = bridge._export_manifest(output, raw, identity)
    assert validated["adoption"] == adopted["adoption"]
    assert set(lanes) == {row["label"] for row in adopted["lanes"]}


def test_adopt_v1_refuses_tampered_legacy_lane(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (_exported, _legacy_path, legacy, _output,
     args) = _adoption_fixture(tmp_path, monkeypatch)
    lane_path = Path(legacy["lanes"][0]["path"])
    lane_path.write_bytes(lane_path.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="file identity changed"):
        bridge.command_adopt_v1(args)


@pytest.mark.parametrize("mutation, message", [
    ("missing", "do not exactly cover"),
    ("duplicate", "duplicate lane identity"),
])
def test_adopt_v1_refuses_missing_or_duplicate_lane(
    tmp_path: Path,
    monkeypatch,
    mutation: str,
    message: str,
) -> None:
    (_exported, legacy_path, legacy, _output,
     args) = _adoption_fixture(tmp_path, monkeypatch)
    if mutation == "missing":
        legacy["lanes"].pop()
    else:
        legacy["lanes"].append(dict(legacy["lanes"][0]))
    legacy_path.write_text(json.dumps(legacy, indent=2, sort_keys=True) + "\n")

    with pytest.raises(ValueError, match=message):
        bridge.command_adopt_v1(args)


@pytest.mark.parametrize("field, value", [
    ("magic", "not-v1"),
    ("version", 2),
    ("tool_sha256", "0" * 64),
])
def test_adopt_v1_requires_exact_frozen_manifest_provenance(
    tmp_path: Path,
    monkeypatch,
    field: str,
    value,
) -> None:
    (_exported, legacy_path, legacy, _output,
     args) = _adoption_fixture(tmp_path, monkeypatch)
    legacy[field] = value
    legacy_path.write_text(json.dumps(legacy, indent=2, sort_keys=True) + "\n")

    with pytest.raises(ValueError, match="frozen-v1|preserved v1"):
        bridge.command_adopt_v1(args)


@pytest.mark.parametrize("mutation, message", [
    ("cascade_path", "cascade file identity changed"),
    ("cascade_file_sha256", "cascade file identity changed"),
    ("cascade_authoritative_sha256", "cascade metadata differs"),
    ("cascade_run_policy_sha256", "cascade metadata differs"),
    ("lane_semantic_sha256", "lane .* differs from cascade"),
])
def test_bound_cascade_replay_rejects_manifest_provenance_mutation(
    tmp_path: Path,
    monkeypatch,
    mutation: str,
    message: str,
) -> None:
    exported = _export(tmp_path, monkeypatch)
    out_dir = exported[-1]
    manifest = json.loads((out_dir / "lanes.json").read_text())
    if mutation == "cascade_path":
        manifest["cascade"]["path"] = manifest["lanes"][0]["path"]
    elif mutation == "cascade_file_sha256":
        manifest["cascade"]["file_sha256"] = "0" * 64
    elif mutation == "cascade_authoritative_sha256":
        manifest["cascade"]["authoritative_sha256"] = "0" * 64
    elif mutation == "cascade_run_policy_sha256":
        manifest["cascade"]["run_policy_sha256"] = "0" * 64
    else:
        manifest["lanes"][0]["cascade_lane_semantic_sha256"] = "0" * 64
    path = tmp_path / f"mutated-{mutation}.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    raw, identity = bridge._stable_bytes(path)
    payload, lanes = bridge._export_manifest(path, raw, identity)

    with pytest.raises(ValueError, match=message):
        bridge._replay_export_cascade(payload, lanes)


def _official_union(manifest: dict, path: Path) -> Path:
    specs = [
        merge_e023b.SourceSpec(row["label"], Path(row["path"]))
        for row in manifest["lanes"]
    ]
    sources = merge_e023b.load_sources(specs)
    payload = merge_e023b.build_union(sources)
    merge_e023b.write_json_atomic(
        path, payload,
        source_paths=tuple(source.path for source in sources))
    return path


def _observer_report(path: Path, overlay) -> Path:
    path.write_text(json.dumps({
        "authoritative_sha256": feedbackstate.authoritative_digest(overlay),
        "profile": overlay.envelope.profile,
        "config_sha256": overlay.envelope.config_sha256,
        "baseline": {"file_sha256": overlay.baseline.file_sha256},
        "summary": overlay.summary(),
    }, indent=2, sort_keys=True) + "\n")
    return path


def _bound_audit_inputs(
    tmp_path: Path,
    monkeypatch,
    *,
    unfinished_lane: int | None = None,
):
    (descriptor, framed, coarse, native, _cascade_state, _args,
     out_dir) = _export(tmp_path, monkeypatch)
    manifest = json.loads((out_dir / "lanes.json").read_text())
    lane_by_label = {
        row["label"]: (Path(row["path"]), lane)
        for row, lane in zip(manifest["lanes"], (coarse, native), strict=True)
    }
    union_path = _official_union(manifest, tmp_path / "portfolio.json")

    runs = []
    reports = []
    for index, (label, (baseline_path, baseline)) in enumerate(
            lane_by_label.items()):
        profile = (
            feedbackstate.PROFILE_REFINE
            if index == unfinished_lane else feedbackstate.PROFILE_CONTROL)
        overlay = feedback.create_session(
            baseline_path, baseline,
            profile=profile,
            certificate_union=union_path)
        state_path = tmp_path / f"{label}-e024.pkl"
        feedbackstate.save_session(
            state_path, overlay, baseline, baseline_path=baseline_path)
        runs.append(f"{label}={state_path}")
        observer_path = _observer_report(
            tmp_path / f"{label}-e024.json", overlay)
        reports.append(f"{label}={observer_path}")

    cells = compose.compose_page(
        framed["payload_bits"], descriptor.spec(), descriptor.seed,
        page=0).cell_values
    dots = np.repeat(
        np.repeat(cells, descriptor.cell_dots, axis=0),
        descriptor.cell_dots, axis=1)
    ground_truth = tmp_path / "ground-truth.npy"
    np.save(ground_truth, dots)
    ground_truth_sha256 = hashlib.sha256(
        ground_truth.read_bytes()).hexdigest()
    monkeypatch.setattr(bridge, "_descriptor", lambda _format_id: descriptor)

    report_path = tmp_path / "portfolio-audit.json"
    args = SimpleNamespace(
        run=runs,
        report=reports,
        baseline=[],
        export_manifest=out_dir / "lanes.json",
        certificate_union=union_path,
        ground_truth=ground_truth,
        ground_truth_sha256=ground_truth_sha256,
        manifest=None,
        out=report_path,
    )
    return manifest, args


def test_bound_audit_proves_exact_lanes_union_reports_and_blind_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest, args = _bound_audit_inputs(tmp_path, monkeypatch)
    loaded = []
    original_load = bridge.feedbackstate.load_session

    def observed_load(*args, **kwargs):
        result = original_load(*args, **kwargs)
        loaded.append(Path(args[0]).resolve())
        return result

    original_truth = bridge._ground_truth

    def observed_truth(*args, **kwargs):
        assert len(loaded) == len(manifest["lanes"])
        return original_truth(*args, **kwargs)

    monkeypatch.setattr(bridge.feedbackstate, "load_session", observed_load)
    monkeypatch.setattr(bridge, "_ground_truth", observed_truth)

    result = bridge.command_audit(args)
    report = json.loads(args.out.read_text())

    assert result == 0
    assert report["magic"] == bridge.AUDIT_MAGIC
    assert report["version"] == bridge.VERSION
    assert report["status"] == "QUALIFIED_BOUND"
    assert report["binding"]["mode"] == "bound_e023c_composition"
    assert report["binding"]["qualified"] is True
    assert report["binding"]["cascade"]["source_closure"]["matches"]
    assert report["binding"]["cascade"]["lane_count"] == 2
    assert set(report["binding"]["cascade"]["lanes"]) == {
        row["label"] for row in manifest["lanes"]}
    assert report["binding"]["certificate_union"][
        "certificate_count"] == manifest["cascade"][
            "certificate_union"]["count"]
    assert report["blind_boundary"] == {
        "all_non_truth_inputs_replayed_and_frozen_before_ground_truth": True,
        "ground_truth_use": "post-hoc certificate correctness only",
    }
    assert report["gates_ok"]
    assert all(report["gates"].values())
    assert report["gates"][
        "manifest_referenced_cascade_replayed_and_matches"]
    assert report["gates"]["all_runs_reached_fixed_point"]
    assert report["global_effect"] == {
        "gained": [], "gained_count": 0,
        "lost": [], "lost_count": 0,
        "changed": [], "changed_count": 0,
        "yield_delta": 0,
    }
    assert report["global_ground_truth"]["wrong_count"] == 0
    assert report["final_portfolio"]["conflict_free"]
    assert report["final_portfolio"]["support_histogram"]["2"] == (
        manifest["lanes"][0]["certified"])
    assert all(
        {key: row["generation_zero"][key]
         for key in ("count", "set_sha256", "bits_sha256")}
        == report["binding"]["certificate_union"]["certificate_identity"]
        for row in report["runs"].values())


def test_bound_audit_refuses_an_unfinished_e024_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _manifest, args = _bound_audit_inputs(
        tmp_path, monkeypatch, unfinished_lane=0)

    assert bridge.command_audit(args) == 3
    report = json.loads(args.out.read_text())
    assert report["status"] == "FAILED_BOUND"
    assert report["gates_ok"] is False
    assert report["gates"]["all_runs_reached_fixed_point"] is False
    assert sum(not row["fixed_point"] for row in report["runs"].values()) == 1


def test_unbound_audit_is_explicitly_observer_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (descriptor, framed, coarse, _native, _cascade_state, _args,
     out_dir) = _export(tmp_path, monkeypatch)
    manifest = json.loads((out_dir / "lanes.json").read_text())
    lane = manifest["lanes"][0]
    baseline_path = Path(lane["path"])
    overlay = feedback.create_session(
        baseline_path, coarse, profile=feedbackstate.PROFILE_CONTROL)
    state_path = tmp_path / "observer-only.pkl"
    feedbackstate.save_session(
        state_path, overlay, coarse, baseline_path=baseline_path)

    cells = compose.compose_page(
        framed["payload_bits"], descriptor.spec(), descriptor.seed,
        page=0).cell_values
    dots = np.repeat(
        np.repeat(cells, descriptor.cell_dots, axis=0),
        descriptor.cell_dots, axis=1)
    ground_truth = tmp_path / "observer-ground-truth.npy"
    np.save(ground_truth, dots)
    monkeypatch.setattr(bridge, "_descriptor", lambda _format_id: descriptor)

    report_path = tmp_path / "observer-audit.json"
    result = bridge.command_audit(SimpleNamespace(
        run=[f"observer={state_path}"], report=[], baseline=[],
        export_manifest=None, certificate_union=None,
        ground_truth=ground_truth,
        ground_truth_sha256=hashlib.sha256(
            ground_truth.read_bytes()).hexdigest(),
        manifest=None, out=report_path,
    ))
    report = json.loads(report_path.read_text())

    assert result == 0
    assert report["status"] == "OBSERVED_UNBOUND"
    assert report["binding"] == {
        "mode": "unbound_observer",
        "qualified": False,
        "reason": (
            "No export manifest or official E023b union was supplied; "
            "this report audits only the explicitly supplied E024 states."),
    }
    assert report["gates_ok"] is True
    assert "every_generation_zero_equals_official_union" not in report["gates"]


def test_bound_audit_requires_one_report_per_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="one observer report per run"):
        bridge.command_audit(SimpleNamespace(
            run=[f"lane={tmp_path / 'state.pkl'}"],
            report=[], baseline=[],
            export_manifest=tmp_path / "lanes.json",
            certificate_union=tmp_path / "union.json",
            ground_truth=tmp_path / "truth.npy",
            ground_truth_sha256=None, manifest=None,
            out=tmp_path / "audit.json",
        ))


@pytest.mark.parametrize("ground_truth_sha256", [None, "bad", "A" * 64])
def test_bound_audit_requires_valid_frozen_ground_truth_digest(
    tmp_path: Path,
    ground_truth_sha256,
) -> None:
    with pytest.raises(ValueError, match="valid 64-hex"):
        bridge.command_audit(SimpleNamespace(
            run=[f"lane={tmp_path / 'state.pkl'}"],
            report=[f"lane={tmp_path / 'report.json'}"], baseline=[],
            export_manifest=tmp_path / "lanes.json",
            certificate_union=tmp_path / "union.json",
            ground_truth=tmp_path / "truth.npy",
            ground_truth_sha256=ground_truth_sha256,
            manifest=None, out=tmp_path / "audit.json",
        ))


def test_export_lane_identity_prevents_same_level_collisions() -> None:
    scale = SimpleNamespace(ordinal=0)
    first = SimpleNamespace(
        level_id="coarse", lane_kind="primary", lane_id="a" * 64)
    second = SimpleNamespace(
        level_id="coarse", lane_kind="primary", lane_id="b" * 64)
    first_label, first_name = bridge._lane_export_tokens(first, scale)
    second_label, second_name = bridge._lane_export_tokens(second, scale)
    assert first_label != second_label
    assert first_name != second_name
    assert first.lane_id in first_name
    assert second.lane_id in second_name


def test_export_refuses_any_generated_label_or_path_collision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _descriptor, _framed, coarse, native = _receiver_lanes(tmp_path)
    cascade = _cascade(coarse, native)
    source = tmp_path / "cascade.pkl"
    source.write_bytes(b"authenticated-cascade-fixture")
    monkeypatch.setattr(
        bridge.cascade_state, "load_session", lambda _path: cascade)
    monkeypatch.setattr(
        bridge.cascade_state, "authoritative_digest", lambda _state: "c" * 64)
    monkeypatch.setattr(
        bridge, "_lane_export_tokens",
        lambda _meta, _scale: ("duplicate", "duplicate.pkl"))

    with pytest.raises(ValueError, match="collide"):
        bridge.command_export(SimpleNamespace(
            cascade=source, out_dir=tmp_path / "lanes", manifest_out=None))


def test_portfolio_refuses_conflicting_certificate_values() -> None:
    clean, merged = bridge._portfolio({
        "coarse": {(0, 1, 2): (8, b"\x01")},
        "native": {(0, 1, 2): (8, b"\x01")},
    })
    assert clean["conflict_free"]
    assert merged == {(0, 1, 2): (8, b"\x01")}

    conflict, merged = bridge._portfolio({
        "coarse": {(0, 1, 2): (8, b"\x01")},
        "native": {(0, 1, 2): (8, b"\x02")},
    })
    assert not conflict["conflict_free"]
    assert conflict["conflict_count"] == 1
    assert merged is None
