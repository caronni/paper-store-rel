"""HCAL-R1 differential: the PostScript encoder the printer executes vs
``report.encode_report_payload``, executed under ghostscript.

The printed self-report has three encoders (Python encoder, Python
template, PostScript). The template is pinned to the encoder in
test_characterize_report_anchors; this module executes the emitted
PostScript verbatim against a stubbed device matrix and asserts the
160-byte record equals the Python encoding of the same device — including
the scenarios that drifted before the 2026-07-30 fix (ImagingBBox quad
offsets, truncation bits, fabricated revision, out-of-range wraps).

Gated: set HOLO_RUN_GS_TESTS=1 with ghostscript on PATH.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess

import numpy as np
import pytest

from holo.characterize import emit, model
from holo.characterize.report import (
    DeviceSelfReport,
    encode_report_payload,
    payload_to_modules,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_GS_TESTS") != "1" or shutil.which("gs") is None,
    reason="gs differential needs HOLO_RUN_GS_TESTS=1 and ghostscript",
)

CAL_IDENTITY = model.Identity(
    stage="calibration", kind="bw", copy_index=3, request_code=2,
    candidate_codes=(1, 2, 3),
    layout_digest=hashlib.sha256(b"gs-cal").hexdigest(),
)
DISC_IDENTITY = model.Identity(
    stage="discovery", kind="color", copy_index=1, request_code=0,
    candidate_codes=model.discovery_candidate_codes("color"),
    layout_digest=hashlib.sha256(b"gs-disc").hexdigest(),
)
RECORDS = [
    {"index": index, "x_layout_dots": 100 + 3000 * index,
     "y_layout_dots": 200, "module_layout_dots": 6,
     "width_modules": 380, "height_modules": 10}
    for index in (0, 1)
]

_FULL_DEV2 = (
    "<< /HWResolution [1200 1200] /PageSize [595 842] "
    "/ImagingBBox [12 12 583 830] /Duplex false /Tumble true "
    "/ProcessColorModel /DeviceCMYK >>"
)


def _device(**overrides) -> DeviceSelfReport:
    base = dict(
        language_level=3, default_resolution=(600, 600),
        effective_resolution=(1200, 1200), page_size_points=(595, 842),
        imaging_bbox=(12, 12, 583, 830), duplex=False, tumble=True,
        process_color_model="DeviceCMYK", product="HCAL Test Printer",
        version="1.4", revision=42, serial="SN0001",
        print_nonce=123456789,
    )
    base.update(overrides)
    return DeviceSelfReport(**base)


def _stub_lines(
    *,
    product: str | None = "(HCAL Test Printer)",
    version: str | None = "(1.4)",
    revision: str | None = "42",
    serial: str | None = "(SN0001)",
    realtime: str = "123456789",
    languagelevel: str = "3",
    dev1: str = "<< /HWResolution [600 600] >>",
    dev2: str = _FULL_DEV2,
) -> tuple[list[str], list[str]]:
    pre = [
        f"/languagelevel {languagelevel} def",
        f"/realtime {realtime} def",
        f"/DEV1 {dev1} def",
        "/currentpagedevice { DEV1 } bind def",
    ]
    for name, value in (("product", product), ("version", version),
                        ("revision", revision)):
        if value is not None:
            pre.append(f"/{name} {value} def")
    pre.append("/statusdict 10 dict def statusdict begin")
    if serial is not None:
        pre.append(f"/serialnumber {{ {serial} }} def")
    pre.append("end")
    mid = [f"/DEV2 {dev2} def", "/currentpagedevice { DEV2 } bind def"]
    return pre, mid


def _run_gs(lines: list[str], *, begin: str, end: str,
            tmp_path) -> list[str]:
    job = tmp_path / "hcal_differential.ps"
    job.write_text("\n".join(lines) + "\n", encoding="ascii")
    proc = subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER",
         "-sDEVICE=nullpage", str(job)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert begin in proc.stdout and end in proc.stdout, (
        f"gs run failed\nstdout: {proc.stdout[-2000:]}"
        f"\nstderr: {proc.stderr[-2000:]}"
    )
    return proc.stdout.split(begin, 1)[1].split(end, 1)[0].split()


def _ps_payload(identity, pre: list[str], mid: list[str],
                tmp_path) -> bytes:
    body = emit._report_postscript(identity, RECORDS, page_height_pt=842.0)
    body = body[:body.index("PAY 159 CRC 255 and put") + 1]
    lines = (
        ["%!PS-Adobe-3.0", "/HARNESS 60 dict def HARNESS begin"]
        + pre + emit._report_prolog() + mid + body
        + ["(BEGINPAY) =", "0 1 159 { PAY exch get = } for",
           "(ENDPAY) =", "flush", "end", "end"]
    )
    values = [int(token) for token in
              _run_gs(lines, begin="BEGINPAY", end="ENDPAY",
                      tmp_path=tmp_path)]
    assert len(values) == 160
    return bytes(values)


def _assert_matches(identity, device: DeviceSelfReport,
                    tmp_path, **stub_overrides) -> None:
    pre, mid = _stub_lines(**stub_overrides)
    ps_bytes = _ps_payload(identity, pre, mid, tmp_path)
    expected = encode_report_payload(identity, device)
    assert ps_bytes.hex() == expected.hex()


def test_full_device_calibration(tmp_path):
    # Non-null /ImagingBBox: the pre-fix PUTQUADAT wrote it at shifted
    # offsets and the record was refused or silently wrong.
    _assert_matches(CAL_IDENTITY, _device(), tmp_path)


def test_full_device_discovery(tmp_path):
    _assert_matches(DISC_IDENTITY, _device(), tmp_path)


@pytest.mark.parametrize("identity", (CAL_IDENTITY, DISC_IDENTITY))
def test_report_has_no_nonstandard_minmax_dependency(identity, tmp_path):
    # Ghostscript exposes non-standard `min`/`max` extensions that real
    # printer RIPs need not implement.  Shadow them with hard failures before
    # the report procedures are parsed so the differential stays portable.
    pre, mid = _stub_lines()
    pre = [
        "/min { (NONSTANDARD-MIN-CALLED) = stop } bind def",
        "/max { (NONSTANDARD-MAX-CALLED) = stop } bind def",
    ] + pre
    ps_bytes = _ps_payload(identity, pre, mid, tmp_path)
    expected = encode_report_payload(identity, _device())
    assert ps_bytes.hex() == expected.hex()


def test_all_unavailable(tmp_path):
    pre = [
        "/languagelevel { 1 0 div } def",
        "/realtime { 1 0 div } def",
        "/currentpagedevice { 1 0 div } bind def",
        "/statusdict 10 dict def",
        "/where { pop false } bind def",
    ]
    mid = ["/currentpagedevice { 1 0 div } bind def"]
    ps_bytes = _ps_payload(CAL_IDENTITY, pre, mid, tmp_path)
    # Pre-fix, a missing /revision still asserted availability for a
    # fabricated 0; the honest record reports every field unavailable.
    expected = encode_report_payload(CAL_IDENTITY, DeviceSelfReport())
    assert ps_bytes.hex() == expected.hex()


def test_truncation_bits_all_three(tmp_path):
    # Pre-fix drift: PS wrote bits 2/4/8 where the decoder defines 1/2/4.
    _assert_matches(
        CAL_IDENTITY,
        _device(product="P" * 80, version="V" * 40, serial="S" * 30),
        tmp_path,
        product="(" + "P" * 80 + ")", version="(" + "V" * 40 + ")",
        serial="(" + "S" * 30 + ")",
    )


def test_exactly_at_capacity_sets_no_truncation(tmp_path):
    _assert_matches(
        CAL_IDENTITY,
        _device(product="P" * 40, version="V" * 18, serial="S" * 16),
        tmp_path,
        product="(" + "P" * 40 + ")", version="(" + "V" * 18 + ")",
        serial="(" + "S" * 16 + ")",
    )


def test_missing_revision_stays_unavailable(tmp_path):
    # ghostscript defines /revision in systemdict, so absence must be
    # simulated by shadowing `where` for that one name.
    pre, mid = _stub_lines(revision=None)
    pre = [
        "/SYSWHERE systemdict /where get def",
        "/where { dup /revision eq { pop false } { SYSWHERE } ifelse }"
        " bind def",
    ] + pre
    ps_bytes = _ps_payload(CAL_IDENTITY, pre, mid, tmp_path)
    expected = encode_report_payload(CAL_IDENTITY, _device(revision=None))
    assert ps_bytes.hex() == expected.hex()


def test_resolution_overflow_goes_unavailable(tmp_path):
    # Pre-fix, 100000 dpi wrapped to 34464 with the availability bit set.
    _assert_matches(
        CAL_IDENTITY, _device(default_resolution=None), tmp_path,
        dev1="<< /HWResolution [100000 600] >>",
    )


def test_bbox_out_of_range_goes_unavailable(tmp_path):
    _assert_matches(
        CAL_IDENTITY, _device(imaging_bbox=None), tmp_path,
        dev2=_FULL_DEV2.replace("[12 12 583 830]", "[0 0 40000 40000]"),
    )


def test_bbox_negative_real_rounds_signed(tmp_path):
    _assert_matches(
        CAL_IDENTITY, _device(imaging_bbox=(-12, 0, 584, 830)), tmp_path,
        dev2=_FULL_DEV2.replace("[12 12 583 830]", "[-12.4 0 583.6 830]"),
    )


def test_negative_realtime_masks_to_31_bits(tmp_path):
    # Pre-fix, realtime -5 wrapped to 4294967291, unencodable in Python.
    _assert_matches(
        CAL_IDENTITY, _device(print_nonce=(-5) & 0x7FFFFFFF), tmp_path,
        realtime="-5",
    )


def test_unknown_color_model_goes_unavailable(tmp_path):
    _assert_matches(
        CAL_IDENTITY, _device(process_color_model=None), tmp_path,
        dev2=_FULL_DEV2.replace("/DeviceCMYK >>", "/DeviceRGBK >>"),
    )


def test_strip_raster_matches_payload_to_modules(tmp_path):
    pre, mid = _stub_lines()
    body = emit._report_postscript(CAL_IDENTITY, RECORDS,
                                   page_height_pt=842.0)
    body = body[:body.index("end")]
    lines = (
        ["%!PS-Adobe-3.0", "/HARNESS 60 dict def HARNESS begin"]
        + pre + emit._report_prolog() + mid
        + ["/rectfill { 4 array astore == } bind def",
           "/gsave { } bind def", "/grestore { } bind def",
           "/translate { pop pop } bind def",
           "/setcmykcolor { pop pop pop pop } bind def"]
        + body
        + ["(BEGINPAY) =", "0 1 159 { PAY exch get = } for", "(ENDPAY) =",
           "(BEGINRECT) =", "0 0 STRIP", "(ENDRECT) =", "flush",
           "end", "end"]
    )
    job = tmp_path / "hcal_raster.ps"
    job.write_text("\n".join(lines) + "\n", encoding="ascii")
    proc = subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER",
         "-sDEVICE=nullpage", str(job)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    out = proc.stdout
    assert "BEGINRECT" in out, proc.stderr[-2000:]
    payload = bytes(
        int(token) for token in
        out.split("BEGINPAY", 1)[1].split("ENDPAY", 1)[0].split()
    )
    height, width = 10, 380
    ps_modules = np.zeros((height, width), dtype=np.uint8)
    for line in out.split("BEGINRECT", 1)[1].split("ENDRECT", 1)[0] \
            .strip().splitlines():
        token = line.strip().strip("[]").split()
        if len(token) != 4:
            continue
        x0, y0, w, h = (int(float(value)) for value in token)
        ps_modules[height - 1 - y0 - (h - 1):height - y0, x0:x0 + w] = 1
    assert np.array_equal(ps_modules, payload_to_modules(payload))
