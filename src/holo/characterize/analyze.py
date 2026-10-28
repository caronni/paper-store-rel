"""Cold-start analysis of one printed characterization scan."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .emit import EMITTER_VERSION, PAGE_MANIFEST_SCHEMA
from .geometry import (
    GeometryError,
    layout_footprint_visibility,
    measure_paper_edges,
    plus_residuals,
    register_blind,
)
from .io import file_sha256, json_bytes, write_new_bytes
from .layout import build_page, verify_page
from .fields import measure_all_fields
from .probes import measure_all_probes, measure_probe
from .model import (
    PAGE_MM,
    REPORT_SCHEMA,
    STIMULUS_SCHEMA,
    Identity,
    semantic_digest,
)
from .summarize import build_page_summary
from .raster import RasterSource
from .report_strips import (
    decode_report_strips,
    normalize_report_strips,
    report_strip_consensus,
)


ANALYZER_VERSION = 4
MAX_IN_MEMORY_HASH_BYTES = 64 << 20


def _refused(
    report: dict[str, Any], code: str, detail: str,
    *, stage: str,
) -> dict[str, Any]:
    report.update({
        "status": "refused",
        "refusal": {
            "code": code,
            "stage": stage,
            "detail": detail,
        },
    })
    report["report_semantic_sha256"] = semantic_digest(report)
    return report


def _capture_record(source: RasterSource) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": None if source.path is None else source.path.name,
        "native_shape": list(source.native_shape),
        "native_dtype": str(source.native_dtype),
        "spatial_shape": list(source.spatial_shape),
        "channels": source.channels,
        "is_color": source.is_color,
        "color_model": source.color_model,
        "memmapped": source.memmapped,
        "sha256": None,
    }
    if source.path is not None:
        record["sha256"] = file_sha256(source.path)
    elif source.native.nbytes <= MAX_IN_MEMORY_HASH_BYTES:
        record["sha256"] = hashlib.sha256(
            np.ascontiguousarray(source.native).tobytes()
        ).hexdigest()
    return record


def _bootstrap_infrastructure() -> list[dict[str, Any]]:
    # Corner and identity geometry is invariant across stage, kind, copy, and
    # request. Regenerating it through the current planner avoids a second,
    # potentially drifting layout description in the analyzer.
    page = build_page(
        stage="discovery", kind="bw", copy_index=0, request_code=0
    )
    return list(page["infrastructure"])


def _identity_dict(identity: Identity) -> dict[str, Any]:
    return identity.to_dict()


def _compute_device_footing(device: Mapping[str, Any]) -> dict[str, Any]:
    """Bind copies to the same reported interpreter/device configuration.

    The per-impression nonce proves the two strips came from one interpreter
    run but must not prevent aggregation across separately printed copies.
    All other readback, including explicit unavailability and truncation, is
    part of the stable footing.
    """

    stable = {
        str(key): value
        for key, value in device.items()
        if key != "print_nonce"
    }
    return {
        "fields": stable,
        "semantic_sha256": semantic_digest(stable),
    }


def _coerce_manifest(
    manifest: str | Path | Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, Path | None]:
    if manifest is None:
        return None, None
    path: Path | None = None
    if isinstance(manifest, (str, Path)):
        path = Path(manifest)
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = manifest
    if not isinstance(value, Mapping):
        raise ValueError("page manifest must be a JSON object")
    value = dict(value)
    if value.get("schema") != PAGE_MANIFEST_SCHEMA:
        raise ValueError(
            f"manifest schema must be exactly {PAGE_MANIFEST_SCHEMA!r}"
        )
    if (
        value.get("schema_version") != EMITTER_VERSION
        or value.get("emitter_version") != EMITTER_VERSION
        or value.get("stimulus_schema") != STIMULUS_SCHEMA
    ):
        raise ValueError("manifest version/stimulus binding is not current")
    page = value.get("page")
    if not isinstance(page, dict):
        raise ValueError("page manifest has no page object")
    verify_page(page)
    if path is not None:
        postscript = value.get("postscript", {})
        relative = postscript.get("path")
        expected = postscript.get("sha256")
        if relative and expected:
            ps_path = path.parent / str(relative)
            if ps_path.exists() and file_sha256(ps_path) != expected:
                raise ValueError("page manifest PostScript hash mismatch")
    return value, path


def _required_integrity_visible(
    source: RasterSource,
    affine: np.ndarray,
    page: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any]]:
    sentinels = [
        row for row in page["probes"] if row["probe_id"] == "end"
    ]
    if len(sentinels) != 1:
        return (
            False,
            "canonical page does not have exactly one end sentinel",
            {},
        )
    visible, _fraction = layout_footprint_visibility(
        source, affine, sentinels[0]
    )
    if not visible:
        return False, "end sentinel is outside the captured raster", {}
    paper_rows = [
        row for row in page["probes"] if row["group"] == "background"
    ]
    paper = [
        measure_probe(source, affine, row) for row in paper_rows
    ]
    end = measure_probe(source, affine, sentinels[0])
    paper_density = [
        float(row["density_median"])
        for row in paper if row.get("status") == "ok"
    ]
    detail = {"end_sentinel": end, "paper_witnesses": paper}
    if not paper_density or end.get("status") != "ok":
        return False, "integrity witnesses are unobservable", detail
    baseline = float(np.median(paper_density))
    detail["paper_density_baseline"] = baseline
    if end.get("density_median") is None:
        return False, "end sentinel density is unavailable", detail
    separation = float(end["density_median"]) - baseline
    detail["end_density_separation"] = separation
    if separation < 0.10:
        return False, "end sentinel ink is missing or unresolved", detail
    return True, None, detail


def analyze_scan(
    scan: str | Path | np.ndarray | RasterSource,
    *,
    scan_dpi_x: float,
    scan_dpi_y: float,
    manifest: str | Path | Mapping[str, Any] | None = None,
    footing: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Analyze one scan, starting with no trusted manifest or orientation.

    True scanner DPI is mandatory. A supplied current page manifest tightens
    content binding but is not needed to identify and regenerate the page.
    All expected hard-gate failures return a structured refused report.
    """

    if (
        not math.isfinite(scan_dpi_x)
        or not math.isfinite(scan_dpi_y)
        or scan_dpi_x <= 0
        or scan_dpi_y <= 0
    ):
        raise ValueError("true scanner DPI values must be finite and positive")
    own_source = not isinstance(scan, RasterSource)
    source = RasterSource(scan) if own_source else scan
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "schema_version": ANALYZER_VERSION,
        "analyzer_version": ANALYZER_VERSION,
        "status": "running",
        "scan_dpi": [float(scan_dpi_x), float(scan_dpi_y)],
        "scanner_dpi_authority": "operator-declared true capture DPI",
        "capture": _capture_record(source),
        "operator_footing": {
            str(key): str(value)
            for key, value in (footing or {}).items()
            if str(value).strip()
        },
    }
    try:
        try:
            supplied_manifest, manifest_path = _coerce_manifest(manifest)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return _refused(
                report, "manifest_invalid", str(exc), stage="binding"
            )
        report["supplied_manifest"] = (
            None if supplied_manifest is None
            else {
                "path": (
                    None if manifest_path is None else manifest_path.name
                ),
                "sha256": (
                    None if manifest_path is None
                    else file_sha256(manifest_path)
                ),
                "schema": supplied_manifest["schema"],
                "page_semantic_sha256": supplied_manifest["page"][
                    "semantic_sha256"
                ],
            }
        )

        infrastructure = _bootstrap_infrastructure()
        try:
            affine, geometry = register_blind(
                source,
                scan_dpi_x,
                scan_dpi_y,
                corner_layout=infrastructure,
            )
        except (GeometryError, ValueError) as exc:
            return _refused(
                report, "corner_registration_failed", str(exc),
                stage="registration",
            )
        report["geometry"] = geometry

        report_regions = [
            row for row in infrastructure
            if row.get("kind") == "machine_report"
        ]
        try:
            report_observations = decode_report_strips(
                source, affine, report_regions
            )
        except (GeometryError, ValueError, TypeError) as exc:
            return _refused(
                report, "machine_report_decode_failed", str(exc),
                stage="self-report",
            )
        printed_report, report_consensus = report_strip_consensus(
            report_observations
        )
        report["machine_report"] = normalize_report_strips(
            report_observations
        )
        if printed_report is None:
            return _refused(
                report,
                "machine_report_consensus_failed",
                str(report_consensus.get("status")),
                stage="self-report",
            )
        wire_identity = printed_report.identity

        try:
            page = build_page(
                stage=wire_identity.stage,
                kind=wire_identity.kind,
                copy_index=wire_identity.copy_index,
                request_code=wire_identity.request_code,
                candidate_codes=wire_identity.resolved_candidate_codes,
            )
            verify_page(page)
            identity = Identity.from_page(page)
        except (KeyError, ValueError) as exc:
            return _refused(
                report, "canonical_regeneration_failed", str(exc),
                stage="binding",
            )
        if not wire_identity.matches(identity):
            return _refused(
                report,
                "printed_identity_mismatch",
                (
                    "the report strip's compact identity does not match "
                    "the regenerated current page"
                ),
                stage="binding",
            )
        report["page_identity"] = _identity_dict(identity)
        device_readback = printed_report.device_readback.to_dict()
        report["device_footing"] = _compute_device_footing(device_readback)
        if (
            supplied_manifest is not None
            and supplied_manifest["page"]["semantic_sha256"]
            != page["semantic_sha256"]
        ):
            return _refused(
                report,
                "manifest_identity_mismatch",
                "supplied page plan differs from printed identity",
                stage="binding",
            )
        report["page_plan_semantic_sha256"] = page["semantic_sha256"]

        if identity.kind == "color" and not source.is_color:
            return _refused(
                report,
                "color_scan_required",
                "a color characterization page needs at least three channels",
                stage="capture",
            )
        integrity_ok, integrity_reason, integrity_detail = (
            _required_integrity_visible(source, affine, page)
        )
        report["integrity_gate"] = integrity_detail
        if not integrity_ok:
            return _refused(
                report, "page_integrity_unobservable",
                str(integrity_reason), stage="visibility",
            )

        report["geometry"]["internal_plus"] = plus_residuals(
            source, affine, page["infrastructure"]
        )
        report["geometry"]["paper_edges"] = measure_paper_edges(
            source, affine, PAGE_MM
        )
        fields = measure_all_fields(source, affine, page["fields"])
        probes = measure_all_probes(source, affine, page["probes"])
        report["field_measurements"] = fields
        report["probe_measurements"] = probes
        report["summary"] = build_page_summary(
            page=page,
            geometry=report["geometry"],
            fields=fields,
            probes=probes,
        )
        report["status"] = "ok"
        report["evidence_scope"] = {
            "supervised_known_stimuli": True,
            "production_receiver_claim": False,
            "request_footing": page["request"],
            "stage": page["stage"],
            "kind": page["kind"],
            "copy_index": page["copy_index"],
        }
        report["report_semantic_sha256"] = semantic_digest(report)
        return report
    finally:
        if own_source:
            source.close()


def write_report(
    output_dir: str | Path,
    report: dict[str, Any],
) -> Path:
    """Exclusively write a content-addressed analysis report."""

    expected = report.get("report_semantic_sha256")
    payload_without_digest = dict(report)
    payload_without_digest.pop("report_semantic_sha256", None)
    if expected != semantic_digest(payload_without_digest):
        raise ValueError("report semantic digest mismatch")
    identity = report.get("page_identity", {})
    kind = identity.get("kind", "unknown")
    stage = identity.get("stage", "refused")
    copy_index = int(identity.get("copy_index", 0))
    name = (
        f"hcal-report-{stage}-{kind}-copy{copy_index:04d}-"
        f"{str(expected)[:16]}.json"
    )
    path = Path(output_dir) / name
    write_new_bytes(path, json_bytes(report))
    return path


__all__ = [
    "ANALYZER_VERSION",
    "analyze_scan",
    "write_report",
]
