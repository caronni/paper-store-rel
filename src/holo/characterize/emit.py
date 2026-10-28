"""Standalone PostScript and manifest emitter for characterization sheets.

This module consumes only the fixed characterization page plan.  It does not
call the production generator and does not emit production payload coupons.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .io import json_bytes, write_new_bytes
from .layout import build_page, verify_page
from .model import (
    BASE_DPI,
    CANDIDATES_BY_CODE,
    KIND_CODES,
    LAYOUT_VERSION,
    REQUEST_CODES,
    REQUEST_DPI,
    REQUEST_NAMES,
    STIMULUS_SCHEMA,
    Identity,
    semantic_digest,
    validate_shortlist,
)
from .patterns import expand_state_planes, field_states, pattern_bits
from .postscript import PageDocument
from .report import (
    REPORT_CRC_OFFSET,
    REPORT_HEIGHT_MODULES,
    REPORT_WIDTH_MODULES,
    postscript_field_lines,
    postscript_strip_lines,
    report_template,
)


PAGE_MANIFEST_SCHEMA = "holo/characterize/page-manifest/v2"
BUNDLE_SCHEMA = "holo/characterize/bundle/v2"
EMITTER_VERSION = 2
DEFAULT_MAX_JOB_BYTES = 128 << 20


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _comment_token(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")


def _report_prolog() -> list[str]:
    """Capture default device state before this job's setpagedevice."""

    return [
        "% HCAL-R1 pre-request device snapshot",
        "/HCR 240 dict def HCR begin",
        "/CMBUF 192 string def /PROBUF 192 string def",
        "/VERBUF 192 string def /SNBUF 192 string def",
        "/TRY { /DFLT exch def mark exch stopped",
        "  { cleartomark DFLT }",
        "  { counttomark 1 eq { exch pop }",
        "    { cleartomark DFLT } ifelse } ifelse } bind def",
        "/PDD { currentpagedevice } 1 dict TRY def",
        "/LLOK false def",
        "/LLV { languagelevel /LLOK true def } 0 TRY def",
        "end",
    ]


def _report_postscript(
    identity: Identity,
    records: Iterable[Mapping[str, Any]],
    *,
    page_height_pt: float,
) -> list[str]:
    """Build one live payload and draw both compact report strips."""

    placements = sorted(
        (
            int(record["index"]),
            int(record["x_layout_dots"]),
            int(record["y_layout_dots"]),
            int(record["module_layout_dots"]),
            int(record["width_modules"]),
            int(record["height_modules"]),
        )
        for record in records
    )
    if [row[0] for row in placements] != [0, 1]:
        raise ValueError("page must carry report strip placements 0 and 1")
    if any(
        row[3:] != (6, REPORT_WIDTH_MODULES, REPORT_HEIGHT_MODULES)
        for row in placements
    ):
        raise ValueError("machine report geometry is not current HCAL-R1")

    template = report_template(identity).hex()
    lines = [
        "% HCAL-R1 effective-device snapshot and compact binary report",
        "HCR begin",
        f"<{template}> /PAY exch def",
        "/AV 0 def /TR 0 def",
        "/SETAV { /B exch def /AV AV B or def } bind def",
        "/PUT16AT { /O exch def /V exch def",
        "  PAY O V -8 bitshift 255 and put",
        "  PAY O 1 add V 255 and put } bind def",
        "/PUT32AT { /O exch def /V exch def",
        "  PAY O V -24 bitshift 255 and put",
        "  PAY O 1 add V -16 bitshift 255 and put",
        "  PAY O 2 add V -8 bitshift 255 and put",
        "  PAY O 3 add V 255 and put } bind def",
        # PUT16AT rebinds /O in the same HCR dict, so the pair/quad walkers
        # must not keep their own state under /O (the pre-fix quad wrote
        # ImagingBBox at offsets 58,60,64,70 instead of 58,60,62,64).
        "/PUTPAIRAT { /PO exch def /PA exch def",
        "  PA 0 get PO PUT16AT PA 1 get PO 2 add PUT16AT } bind def",
        "/PUTQUADAT { /QO exch def /QA exch def",
        "  0 1 3 { /QI exch def QA QI get QO QI 2 mul add PUT16AT } for",
        "  } bind def",
        "/PUTSLOT { /TB exch def /MAX exch def /O exch def",
        # `min` is a Ghostscript extension, not a PostScript operator.  Keep
        # this comparison explicit so the live report runs on printer RIPs.
        "  /LO exch def /S exch def /N S length dup MAX gt { pop MAX } if def",
        "  PAY LO N put PAY O S 0 N getinterval putinterval",
        "  S length MAX gt { /TR TR TB or def } if } bind def",
        # Out-of-range values become UNAVAILABLE, never silent 16-bit wraps:
        # pairs are unsigned (>HH), the bbox quad is signed (>hhhh), matching
        # the Python encoder's refusals.
        "/INR16 { dup 0 ge exch 65535 le and } bind def",
        "/INS16 { dup -32768 ge exch 32767 le and } bind def",
        "/GETPAIR { /K exch def /D exch def /PAIRGOOD false def",
        "  { D K get dup 0 get round cvi exch 1 get round cvi",
        "    2 array astore",
        "    dup dup 0 get INR16 exch 1 get INR16 and",
        "    /PAIRGOOD exch def } [0 0] TRY",
        "  PAIRGOOD } bind def",
        "/GETQUAD { /K exch def /D exch def /QUADGOOD false def",
        "  { D K get dup type /arraytype eq",
        "    { dup length 4 ge",
        "      { dup 0 get round cvi exch dup 1 get round cvi exch",
        "        dup 2 get round cvi exch 3 get round cvi",
        "        4 array astore /QARR exch def /QG true def",
        "        0 1 3 { QARR exch get INS16 QG and /QG exch def } for",
        "        /QUADGOOD QG def QARR }",
        "      { pop [0 0 0 0] } ifelse }",
        "    { pop [0 0 0 0] } ifelse } [0 0 0 0] TRY",
        "  QUADGOOD } bind def",
        "/GETBOOL { /K exch def /D exch def /BOOLGOOD false def",
        "  { D K get dup type /booleantype eq",
        "    { /BOOLGOOD true def { 2 } { 1 } ifelse }",
        "    { pop 0 } ifelse } 0 TRY BOOLGOOD } bind def",
        "/PDE { currentpagedevice } 1 dict TRY def",
        "/RD PDD /HWResolution GETPAIR /RDOK exch def def",
        "/RE PDE /HWResolution GETPAIR /REOK exch def def",
        "/PSZ PDE /PageSize GETPAIR /PSOK exch def def",
        "/IB PDE /ImagingBBox GETQUAD /IBOK exch def def",
        "/DU PDE /Duplex GETBOOL /DUOK exch def def",
        "/TU PDE /Tumble GETBOOL /TUOK exch def def",
        "/CMS { PDE /ProcessColorModel get CMBUF cvs } () TRY def",
        "/CM 0 def",
        "CMS (DeviceGray) eq { /CM 1 def }",
        "  { CMS (DeviceRGB) eq { /CM 2 def }",
        "    { CMS (DeviceCMYK) eq { /CM 3 def }",
        "      { CMS (DeviceN) eq { /CM 4 def } if } ifelse } ifelse } ifelse",
        "/CMOK CM 0 ne def",
        "/PROK false def",
        "/PRO { /product where { /product get }",
        "  { statusdict /product get } ifelse",
        "  dup type /stringtype ne { PROBUF cvs } if",
        "  /PROK true def } () TRY def",
        "/VERK false def",
        "/VER { /version where { /version get }",
        "  { statusdict /version get } ifelse",
        "  dup type /stringtype ne { VERBUF cvs } if",
        "  /VERK true def } () TRY def",
        # An absent /revision stays UNAVAILABLE — the pre-fix fallback
        # asserted availability for a fabricated 0, against the design's
        # "unavailable values remain explicitly unavailable".
        "/RVOK false def",
        "/RV { /revision where",
        "  { /revision get dup type /integertype ne { round cvi } if",
        "    /RVOK true def }",
        "  { 0 } ifelse } 0 TRY def",
        "/SNOK false def",
        "/SN { statusdict /serialnumber get exec",
        "  dup type /stringtype ne { SNBUF cvs } if",
        "  /SNOK true def } () TRY def",
        # realtime can be negative; mask to a non-negative 31-bit value the
        # Python nonce field accepts instead of wrapping through PUT32AT.
        "/NONCEOK false def",
        "/NONCE { realtime dup type /integertype ne { round cvi } if",
        "  16#7FFFFFFF and /NONCEOK true def } 0 TRY def",
        *postscript_field_lines(),
        "/CRC 16#FFFF def",
        "/CRCB { 8 bitshift CRC xor 16#FFFF and /CRC exch def",
        "  8 { CRC 16#8000 and 0 ne",
        "    { CRC 1 bitshift 16#1021 xor } { CRC 1 bitshift } ifelse",
        "    16#FFFF and /CRC exch def } repeat } bind def",
        f"0 1 {REPORT_CRC_OFFSET - 1} {{ PAY exch get CRCB }} for",
        f"PAY {REPORT_CRC_OFFSET} CRC -8 bitshift 255 and put",
        f"PAY {REPORT_CRC_OFFSET + 1} CRC 255 and put",
        *postscript_strip_lines(),
    ]
    for _index, x_dots, y_dots, module, _width, height in placements:
        x_pt = x_dots / BASE_DPI * 72.0
        strip_height_pt = height * module / BASE_DPI * 72.0
        y_pt = page_height_pt - y_dots / BASE_DPI * 72.0 - strip_height_pt
        module_pt = module / BASE_DPI * 72.0
        lines.extend([
            "gsave",
            f"{module_pt:.8f} {module_pt:.8f} scale",
            f"{x_pt / module_pt:.8f} {y_pt / module_pt:.8f} STRIP",
            "grestore",
        ])
    lines.extend(["end", "% HCAL-R1 report complete"])
    return lines


def _emit_planes(
    document: PageDocument,
    planes: Mapping[str, np.ndarray],
    *,
    emission_path: str,
    x_dots: int,
    y_dots: int,
    dpi: tuple[int, int],
) -> None:
    """Render one exact plane set through its declared emission path."""
    values = {
        str(plane): np.asarray(bits, dtype=np.uint8)
        for plane, bits in planes.items()
    }
    if emission_path == "single-plane-imagemask":
        if len(values) != 1:
            raise ValueError(
                "single-plane-imagemask requires exactly one authored plane"
            )
        plane, bits = next(iter(values.items()))
        document.bitmap(
            bits, x_dots=x_dots, y_dots=y_dots, dpi=dpi, plane=plane
        )
        return
    if emission_path == "DeviceCMYK-image":
        document.cmyk_bitmap(
            values, x_dots=x_dots, y_dots=y_dots, dpi=dpi
        )
        return
    if emission_path == "sequential-overprint-opm1":
        for plane in "CMYK":
            if plane in values:
                document.bitmap(
                    values[plane],
                    x_dots=x_dots,
                    y_dots=y_dots,
                    dpi=dpi,
                    plane=plane,
                    overprint=True,
                    opm=True,
                )
        return
    raise ValueError(f"unsupported characterization emission path {emission_path!r}")


def _render_infrastructure(
    document: PageDocument, page: Mapping[str, Any]
) -> None:
    identity = Identity.from_page(page)
    report_records = [
        item for item in page["infrastructure"]
        if item.get("kind") == "machine_report"
    ]
    document.prolog_lines.extend(_report_prolog())
    document.lines.extend(_report_postscript(
        identity,
        report_records,
        page_height_pt=document.page_size_pt[1],
    ))
    for item in page["infrastructure"]:
        kind = str(item["kind"])
        if kind == "machine_report":
            continue
        if kind == "corner_mark":
            bits = pattern_bits({
                "kind": "chiral_corner",
                "w_source_dots": int(item["w_layout_dots"]),
                "h_source_dots": int(item["h_layout_dots"]),
                "params": {
                    "satellites": int(item["satellites"]),
                    "inward": list(item["inward"]),
                    "stroke_dots": 3,
                },
            })
            document.lines.append(
                f"% HC-INFRA corner satellites={int(item['satellites'])}"
            )
            document.bitmap(
                bits,
                x_dots=int(item["x_layout_dots"]),
                y_dots=int(item["y_layout_dots"]),
                dpi=(BASE_DPI, BASE_DPI),
                plane="K",
            )
        elif kind == "geometry_plus":
            bits = pattern_bits({
                "kind": "plus_mark",
                "w_source_dots": int(item["w_layout_dots"]),
                "h_source_dots": int(item["h_layout_dots"]),
                "params": {"stroke_dots": 3},
            })
            document.lines.append(
                f"% HC-INFRA plus index={int(item['index'])}"
            )
            document.bitmap(
                bits,
                x_dots=int(item["x_layout_dots"]),
                y_dots=int(item["y_layout_dots"]),
                dpi=(BASE_DPI, BASE_DPI),
                plane="K",
            )
        elif kind == "annotation_box":
            document.rectangle(
                x_mm=float(item["x_mm"]),
                y_mm=float(item["y_mm"]),
                width_mm=float(item["width_mm"]),
                height_mm=float(item["height_mm"]),
            )
        else:
            raise ValueError(f"unsupported infrastructure kind {kind!r}")


def _render_probes(
    document: PageDocument,
    probes: Iterable[Mapping[str, Any]],
) -> None:
    for probe in probes:
        bits = pattern_bits(probe)
        expected = str(probe["ground_truth_sha256"])
        if _sha256(np.ascontiguousarray(bits).tobytes()) != expected:
            raise ValueError(
                f"{probe['probe_id']}: regenerated probe digest mismatch"
            )
        params = dict(probe.get("params", {}))
        path = str(params.get("path", "single-plane-imagemask"))
        plane_names = tuple(
            str(value) for value in params.get("planes", [probe["plane"]])
        )
        planes = {plane: bits for plane in plane_names}
        document.lines.append(
            f"% HC-PROBE {_comment_token(probe['probe_id'])} PATH {path}"
        )
        _emit_planes(
            document,
            planes,
            emission_path=path,
            x_dots=int(probe["x_source_dots"]),
            y_dots=int(probe["y_source_dots"]),
            dpi=(
                int(probe["source_dpi"][0]),
                int(probe["source_dpi"][1]),
            ),
        )


def _render_fields(document: PageDocument, page: Mapping[str, Any]) -> None:
    carried = {int(code) for code in page["candidate_codes"]}
    for field in page["fields"]:
        code = int(field["candidate_code"])
        if code not in carried:
            raise ValueError(f"{field['field_id']}: field candidate is not carried")
        candidate = CANDIDATES_BY_CODE[code]
        if candidate.candidate_id != str(field["candidate_id"]):
            raise ValueError(f"{field['field_id']}: candidate identity mismatch")
        states = field_states(field, candidate)
        expected = str(field["state_sha256"])
        if _sha256(np.ascontiguousarray(states).tobytes()) != expected:
            raise ValueError(
                f"{field['field_id']}: regenerated state digest mismatch"
            )
        planes = expand_state_planes(states, candidate)
        document.lines.append(
            f"% HC-FIELD {_comment_token(field['field_id'])} "
            f"CANDIDATE {code} PATH {candidate.emission_path}"
        )
        _emit_planes(
            document,
            planes,
            emission_path=candidate.emission_path,
            x_dots=int(field["x_source_dots"]),
            y_dots=int(field["y_source_dots"]),
            dpi=candidate.grid_dpi,
        )


def render_page(page: dict[str, Any]) -> bytes:
    """Render one canonical page plan as a deterministic one-page PS job."""
    verify_page(page)
    request_code = int(page["request_code"])
    if request_code not in REQUEST_NAMES:
        raise ValueError(f"unsupported request code {request_code}")
    request_dpi = REQUEST_DPI[request_code]
    title = (
        f"HOLO characterize {page['stage']} {page['kind']} "
        f"copy {int(page['copy_index'])} request {REQUEST_NAMES[request_code]}"
    )
    document = PageDocument(title=title, request_dpi=request_dpi)
    document.lines.extend([
        f"% HC-STIMULUS-SCHEMA {STIMULUS_SCHEMA}",
        f"% HC-LAYOUT-VERSION {LAYOUT_VERSION}",
        f"% HC-SEMANTIC-SHA256 {page['semantic_sha256']}",
    ])
    probes = list(page["probes"])
    end_sentinels = [
        probe for probe in probes if probe["probe_id"] == "end"
    ]
    if len(end_sentinels) != 1:
        raise ValueError("page must carry exactly one end sentinel")
    _render_infrastructure(document, page)
    _render_probes(
        document,
        [probe for probe in probes if probe["probe_id"] != "end"],
    )
    _render_fields(document, page)
    for annotation in page["annotations"]:
        document.label(
            str(annotation["text"]),
            x_mm=float(annotation["x_mm"]),
            y_mm=float(annotation["y_mm"]),
            size_pt=float(annotation["size_pt"]),
        )
    # The end sentinel is deliberately the final emitted page mark.  Its
    # presence therefore witnesses that the complete content stream arrived.
    _render_probes(document, end_sentinels)
    payload = document.render().encode("ascii")
    if payload.count(b"%%Page:") != 1 or payload.count(b"showpage") != 1:
        raise RuntimeError("characterization jobs must contain exactly one page")
    return payload


def _request_code(value: int | str) -> int:
    if isinstance(value, str):
        if value not in REQUEST_CODES:
            raise ValueError(f"unsupported request footing {value!r}")
        return REQUEST_CODES[value]
    code = int(value)
    if code not in REQUEST_NAMES:
        raise ValueError(f"unsupported request code {code}")
    return code


def _candidate_selection(
    *,
    stage: str,
    kinds: tuple[str, ...],
    candidate_codes: Mapping[str, Iterable[int]] | None,
) -> dict[str, tuple[int, ...] | None]:
    if stage == "discovery":
        if candidate_codes is not None:
            raise ValueError("discovery uses the fixed current candidate registry")
        return {kind: None for kind in kinds}
    if stage != "calibration":
        raise ValueError(f"unsupported stage {stage!r}")
    if candidate_codes is None:
        raise ValueError("calibration requires an explicit candidate shortlist")
    unknown = set(candidate_codes) - set(kinds)
    if unknown:
        raise ValueError(f"candidate mapping has unrequested kinds: {unknown}")
    selected = {
        kind: tuple(int(code) for code in candidate_codes.get(kind, ()))
        for kind in kinds
    }
    for kind, codes in selected.items():
        try:
            selected[kind] = validate_shortlist(kind, codes)
        except ValueError as exc:
            raise ValueError(
                f"calibration shortlist for {kind}: {exc}"
            ) from exc
    return selected


def emit_bundle(
    output_dir: str | Path,
    *,
    stage: str = "discovery",
    copy_index: int = 0,
    request_code: int | str = 0,
    candidate_codes: (
        Mapping[str, Iterable[int]] | Iterable[int] | None
    ) = None,
    kinds: Iterable[str] = ("bw", "color"),
    max_job_bytes: int = DEFAULT_MAX_JOB_BYTES,
) -> dict[str, Any]:
    """Build and exclusively write a characterization evidence bundle.

    Page filenames include the page-plan digest.  Existing files are never
    reused or replaced, even when their bytes would be identical.
    """
    ordered_kinds = tuple(str(kind) for kind in kinds)
    if not ordered_kinds or len(set(ordered_kinds)) != len(ordered_kinds):
        raise ValueError("kinds must be a non-empty unique sequence")
    if any(kind not in KIND_CODES for kind in ordered_kinds):
        raise ValueError(f"unsupported page kinds {ordered_kinds!r}")
    if max_job_bytes <= 0:
        raise ValueError("max_job_bytes must be positive")
    resolved_request = _request_code(request_code)
    selections = _candidate_selection(
        stage=stage,
        kinds=ordered_kinds,
        candidate_codes=candidate_codes,
    )

    rendered: list[dict[str, Any]] = []
    for kind in ordered_kinds:
        page = build_page(
            stage=stage,
            kind=kind,
            copy_index=int(copy_index),
            request_code=resolved_request,
            candidate_codes=selections[kind],
        )
        postscript = render_page(page)
        if len(postscript) > max_job_bytes:
            raise ValueError(
                f"{kind} job is {len(postscript)} bytes, exceeding "
                f"the {max_job_bytes}-byte guard"
            )
        short_digest = str(page["semantic_sha256"])[:16]
        stem = (
            f"hcal-{stage}-{kind}-copy{int(copy_index):04d}-"
            f"{REQUEST_NAMES[resolved_request]}-{short_digest}"
        )
        ps_name = f"{stem}.ps"
        manifest_name = f"{stem}.manifest.json"
        page_manifest = {
            "schema": PAGE_MANIFEST_SCHEMA,
            "schema_version": EMITTER_VERSION,
            "stimulus_schema": STIMULUS_SCHEMA,
            "emitter_version": EMITTER_VERSION,
            "page": page,
            "postscript": {
                "path": ps_name,
                "sha256": _sha256(postscript),
                "bytes": len(postscript),
            },
        }
        manifest_payload = json_bytes(page_manifest)
        rendered.append({
            "kind": kind,
            "page": page,
            "postscript_payload": postscript,
            "page_manifest_payload": manifest_payload,
            "postscript": page_manifest["postscript"],
            "page_manifest": {
                "path": manifest_name,
                "sha256": _sha256(manifest_payload),
                "bytes": len(manifest_payload),
            },
        })

    bundle: dict[str, Any] = {
        "schema": BUNDLE_SCHEMA,
        "schema_version": EMITTER_VERSION,
        "stimulus_schema": STIMULUS_SCHEMA,
        "layout_version": LAYOUT_VERSION,
        "stage": stage,
        "copy_index": int(copy_index),
        "request_code": resolved_request,
        "request": REQUEST_NAMES[resolved_request],
        "pages": [
            {
                "kind": item["kind"],
                "page_semantic_sha256": item["page"]["semantic_sha256"],
                "identity": item["page"]["identity"],
                "postscript": item["postscript"],
                "page_manifest": item["page_manifest"],
            }
            for item in rendered
        ],
    }
    bundle["bundle_semantic_sha256"] = semantic_digest(bundle)
    bundle_name = (
        f"hcal-{stage}-copy{int(copy_index):04d}-"
        f"{REQUEST_NAMES[resolved_request]}-"
        f"{bundle['bundle_semantic_sha256'][:16]}.bundle.json"
    )
    bundle_payload = json_bytes(bundle)

    root = Path(output_dir)
    targets: list[tuple[Path, bytes]] = []
    for item in rendered:
        targets.extend([
            (root / item["postscript"]["path"], item["postscript_payload"]),
            (
                root / item["page_manifest"]["path"],
                item["page_manifest_payload"],
            ),
        ])
    targets.append((root / bundle_name, bundle_payload))
    existing = [str(path) for path, _payload in targets if path.exists()]
    if existing:
        raise FileExistsError(
            "refusing to overwrite existing evidence: " + ", ".join(existing)
        )
    for path, payload in targets:
        write_new_bytes(path, payload)

    result = dict(bundle)
    result["bundle_manifest"] = {
        "path": bundle_name,
        "sha256": _sha256(bundle_payload),
        "bytes": len(bundle_payload),
    }
    return result


__all__ = [
    "BUNDLE_SCHEMA",
    "DEFAULT_MAX_JOB_BYTES",
    "EMITTER_VERSION",
    "PAGE_MANIFEST_SCHEMA",
    "emit_bundle",
    "render_page",
]
