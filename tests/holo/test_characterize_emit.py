from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from holo.characterize.emit import (
    BUNDLE_SCHEMA,
    PAGE_MANIFEST_SCHEMA,
    emit_bundle,
    render_page,
)
from holo.characterize.layout import build_page, verify_page
from holo.characterize.model import (
    CANDIDATES_BY_CODE,
    REQUEST_CODES,
    semantic_digest,
)


def _candidate(kind: str, path: str) -> int:
    return next(
        code
        for code, candidate in CANDIDATES_BY_CODE.items()
        if candidate.page_kind == kind and candidate.emission_path == path
    )


def _calibration_page(
    kind: str, codes: tuple[int, ...], *, request: str = "default"
) -> dict:
    return build_page(
        stage="calibration",
        kind=kind,
        copy_index=7,
        request_code=REQUEST_CODES[request],
        candidate_codes=codes,
    )


def test_render_page_is_deterministic_complete_and_one_page() -> None:
    page = _calibration_page("bw", (_candidate(
        "bw", "single-plane-imagemask"
    ),))

    first = render_page(page)
    second = render_page(page)

    assert first == second
    assert first.startswith(b"%!PS-Adobe-3.0\n")
    assert first.count(b"%%Page:") == 1
    assert first.count(b"showpage") == 1
    assert b"HC-IDENTITY-PANEL" not in first
    assert first.count(b"HCAL-R1 report complete") == 1
    assert first.count(b"48435250") == 1
    assert first.count(b"/STRIP {") == 1
    assert first.count(b"% HC-FIELD ") == len(page["fields"])
    assert first.count(b"% HC-PROBE ") == len(page["probes"])
    assert b"S length dup MAX gt { pop MAX } if" in first
    assert b"S length MAX min" not in first
    pre_request = first.index(b"/PDD { currentpagedevice }")
    request = first.index(b"setpagedevice")
    post_request = first.index(b"/PDE { currentpagedevice }")
    assert pre_request < request < post_request
    assert first.index(b"/RD PDD /HWResolution") > post_request
    assert first.index(b"/RE PDE /HWResolution") > post_request
    assert first.index(b"/PSZ PDE /PageSize") > post_request
    assert first.index(b"/IB PDE /ImagingBBox") > post_request
    assert first.index(b"/DU PDE /Duplex") > post_request
    assert first.index(b"/TU PDE /Tumble") > post_request
    assert first.count(b" STRIP\n") == 2
    assert b"/ASCII85Decode filter /RunLengthDecode filter" in first
    assert page["semantic_sha256"].encode("ascii") in first
    assert first.rfind(b"% HC-PROBE end ") > first.rfind(b"% HC-FIELD ")


def test_requested_resolution_is_guarded_and_color_paths_are_distinct() -> None:
    single = _candidate("color", "single-plane-imagemask")
    composite = _candidate("color", "DeviceCMYK-image")
    sequential = _candidate("color", "sequential-overprint-opm1")
    page = _calibration_page(
        "color", (single, composite, sequential), request="1200x2400"
    )

    postscript = render_page(page)

    assert b"/HWResolution [1200 2400]" in postscript
    assert b"} stopped { } if" in postscript
    assert b"/DeviceCMYK setcolorspace" in postscript
    assert b"setoverprintmode" in postscript
    assert b"true setoverprint" in postscript
    assert b"PATH single-plane-imagemask" in postscript
    assert b"PATH DeviceCMYK-image" in postscript
    assert b"PATH sequential-overprint-opm1" in postscript


# The screen probes ride the colour discovery page and nothing cheaper
# (layout.add_color_discovery), so both halves of the split rebuild it for
# 0.05 s; only the marker half pays the 2.3 s render (2026-09-05).
def _color_screen_controls() -> tuple[dict, list[dict]]:
    page = build_page(
        stage="discovery",
        kind="color",
        copy_index=4,
        request_code=REQUEST_CODES["default"],
    )
    return page, [row for row in page["probes"] if row["group"] == "screen"]


def test_color_screen_paths_hold_prn_content_and_geometry_constant() -> None:
    _page, controls = _color_screen_controls()

    assert {row["probe_id"] for row in controls} == {
        "screen/path/imagemask-C",
        "screen/path/devicecmyk-C",
        "screen/path/devicecmyk-CM",
        "screen/path/opm1-CM",
    }
    assert {row["kind"] for row in controls} == {"entropy_field"}
    assert {row["plane"] for row in controls} == {"K"}
    assert {tuple(row["params"]["planes"]) for row in controls} == {
        ("C",), ("C", "M")
    }
    assert {row["params"]["matched_set"] for row in controls} == {
        "prn-path-v1"
    }
    assert {row["params"]["control_role"] for row in controls} == {
        "imagemask-C",
        "devicecmyk-C",
        "devicecmyk-CM",
        "opm1-CM",
    }
    assert {row["params"]["measurement_feature"] for row in controls} == {
        "luma-density"
    }
    assert {row["params"]["path"] for row in controls} == {
        "single-plane-imagemask",
        "DeviceCMYK-image",
        "sequential-overprint-opm1",
    }
    assert len({row["seed_label"] for row in controls}) == 1
    assert len({row["ground_truth_sha256"] for row in controls}) == 1
    assert len({
        (
            tuple(row["source_dpi"]),
            row["w_source_dots"],
            row["h_source_dots"],
            row["w_layout_dots"],
            row["h_layout_dots"],
        )
        for row in controls
    }) == 1


def test_each_screen_path_is_announced_in_the_postscript() -> None:
    page, controls = _color_screen_controls()

    postscript = render_page(page)

    for row in controls:
        marker = (
            f"% HC-PROBE {row['probe_id']} "
            f"PATH {row['params']['path']}"
        ).encode("ascii")
        assert marker in postscript


def test_emit_bundle_writes_bound_manifests_and_never_overwrites(
    tmp_path: Path,
) -> None:
    bw = _candidate("bw", "single-plane-imagemask")
    color = _candidate("color", "single-plane-imagemask")

    bundle = emit_bundle(
        tmp_path,
        stage="calibration",
        copy_index=3,
        request_code="default",
        candidate_codes={"bw": (bw,), "color": (color,)},
        max_job_bytes=8 << 20,
    )

    assert bundle["schema"] == BUNDLE_SCHEMA
    assert bundle["schema_version"] == 2
    assert [entry["kind"] for entry in bundle["pages"]] == ["bw", "color"]
    assert len(list(tmp_path.iterdir())) == 5
    for entry in bundle["pages"]:
        ps_path = tmp_path / entry["postscript"]["path"]
        manifest_path = tmp_path / entry["page_manifest"]["path"]
        ps_payload = ps_path.read_bytes()
        manifest_payload = manifest_path.read_bytes()
        assert hashlib.sha256(ps_payload).hexdigest() == (
            entry["postscript"]["sha256"]
        )
        assert hashlib.sha256(manifest_payload).hexdigest() == (
            entry["page_manifest"]["sha256"]
        )
        manifest = json.loads(manifest_payload)
        assert manifest["schema"] == PAGE_MANIFEST_SCHEMA
        assert manifest["postscript"] == entry["postscript"]
        verify_page(manifest["page"])

    bundle_path = tmp_path / bundle["bundle_manifest"]["path"]
    assert hashlib.sha256(bundle_path.read_bytes()).hexdigest() == (
        bundle["bundle_manifest"]["sha256"]
    )
    bundle_manifest = json.loads(bundle_path.read_bytes())
    bundle_digest = bundle_manifest.pop("bundle_semantic_sha256")
    assert bundle_digest == semantic_digest(bundle_manifest)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        emit_bundle(
            tmp_path,
            stage="calibration",
            copy_index=3,
            request_code="default",
            candidate_codes={"bw": (bw,), "color": (color,)},
            max_job_bytes=8 << 20,
        )


def test_job_size_guard_fails_before_any_output(tmp_path: Path) -> None:
    bw = _candidate("bw", "single-plane-imagemask")

    with pytest.raises(ValueError, match="exceeding"):
        emit_bundle(
            tmp_path,
            stage="calibration",
            copy_index=0,
            candidate_codes={"bw": (bw,)},
            kinds=("bw",),
            max_job_bytes=128,
        )

    assert not tmp_path.exists() or not tuple(tmp_path.iterdir())
