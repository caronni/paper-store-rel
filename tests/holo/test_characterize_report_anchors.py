"""Format anchors for the characterization instrument (W0 pins).

These are printed-artifact anchors: the HCAL-R1 wire record, the positional
candidate-code registry (codes ride HCAL-R1 bytes 12:20 on paper), the page
layout digests, and the CRC. A mismatch means the printed format moved —
regenerate deliberately, with the reason in the commit message, never to
silence the test.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from holo.characterize import model
from holo.characterize.layout import build_page
from holo.characterize.model import (
    CANDIDATES_BY_CODE,
    REQUEST_CODES,
    discovery_candidate_codes,
    semantic_digest,
)
from holo.characterize.report import (
    DeviceSelfReport,
    REPORT_CRC_OFFSET,
    crc16_ccitt,
    decode_report_payload,
    encode_report_payload,
    report_template,
)


def _cal_identity() -> model.Identity:
    return model.Identity(
        stage="calibration", kind="bw", copy_index=3, request_code=2,
        candidate_codes=(1, 2, 3),
        layout_digest=hashlib.sha256(b"anchor-cal").hexdigest(),
    )


def _disc_identity() -> model.Identity:
    return model.Identity(
        stage="discovery", kind="color", copy_index=0, request_code=0,
        candidate_codes=discovery_candidate_codes("color"),
        layout_digest=hashlib.sha256(b"anchor-disc").hexdigest(),
    )


def _full_device() -> DeviceSelfReport:
    return DeviceSelfReport(
        language_level=3, default_resolution=(600, 600),
        effective_resolution=(1200, 1200), page_size_points=(595, 842),
        imaging_bbox=(12, 12, 583, 830), duplex=False, tumble=True,
        process_color_model="DeviceCMYK", product="HCAL Test Printer",
        version="1.4", revision=42, serial="SN0001", print_nonce=123456789,
    )


def test_crc16_ccitt_known_answers():
    assert crc16_ccitt(b"123456789") == 0x29B1
    assert crc16_ccitt(b"") == 0xFFFF


# Frozen wire bytes: one fully-populated calibration record and one
# all-unavailable discovery record.
_CAL_FULL_HEX = (
    "484352500102010200030300010203000000000098122be8944cf2e5626f6d28"
    "0f0ed8e3025802581fff030301020258025804b004b00253034a000c000c0247"
    "033e0011030600000000002a00000000075bcd154843414c2054657374205072"
    "696e7465720000000000000000000000000000000000000000000000312e3400"
    "0000000000000000000000000000534e30303031000000000000000000009940"
)
_DISC_EMPTY_HEX = (
    "48435250010102000000000000000000000000009b08ef8aabedd70bdf5d8239"
    "bb3886b500000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000de36"
)


def test_encoder_wire_bytes_frozen():
    assert encode_report_payload(
        _cal_identity(), _full_device()
    ).hex() == _CAL_FULL_HEX
    assert encode_report_payload(
        _disc_identity(), DeviceSelfReport()
    ).hex() == _DISC_EMPTY_HEX


def test_encoder_decoder_round_trip_on_anchors():
    for identity, device in (
        (_cal_identity(), _full_device()),
        (_disc_identity(), DeviceSelfReport()),
    ):
        decoded = decode_report_payload(
            encode_report_payload(identity, device)
        )
        assert decoded.identity.stage == identity.stage
        assert decoded.identity.kind == identity.kind
        assert decoded.device_readback == device


def test_report_template_is_encoder_with_zero_crc():
    for identity in (_cal_identity(), _disc_identity()):
        template = report_template(identity)
        reference = bytearray(
            encode_report_payload(identity, DeviceSelfReport())
        )
        reference[REPORT_CRC_OFFSET:] = b"\x00\x00"
        assert template == bytes(reference)


# The candidate registry is positional (code = declaration order) and the
# codes are PRINTED in HCAL-R1 bytes 12:20: the (code, candidate_id) table
# is append-only. Inserting a candidate anywhere but the end renumbers
# every printed strip after it.
_CANDIDATE_TABLE_SHA = (
    "4ff9eb6a24e6c6e7510e182eee6208f48bb32437eaaa18a7f46b7a50d8ca0c5b"
)


def test_candidate_code_table_frozen():
    table = [
        [candidate.code, candidate.candidate_id]
        for candidate in CANDIDATES_BY_CODE.values()
    ]
    assert len(table) == 86
    assert table[0] == [1, "bw-k2-g300-c1-single-plane-imagemask"]
    assert table[33] == [34, "bw-k2-g600-c3x2"]
    assert table[-1] == [86, "color-cmy8-g600-c3-opm1"]
    blob = json.dumps(table, separators=(",", ":")).encode()
    assert hashlib.sha256(blob).hexdigest() == _CANDIDATE_TABLE_SHA, (
        "candidate registry changed: the table is append-only because codes "
        "are printed on paper — regenerate this pin only for appends"
    )


# Full page-plan digests: every stimulus byte, placement, and identity field
# folds into these. Format-axis — a change is a deliberate layout bump.
_PAGE_DIGESTS = {
    ("discovery", "bw", 0):
        "af3ffbfdbe3102e4d0b33b21de792f91ba28f5b9eca835ada4b00288a597fcfc",
    ("discovery", "bw", 1):
        "2b425a78c7b3ae95b9ab55c806b0c445bf730cc809568e655a4c8e526f8cbdc1",
    ("calibration", "bw", 0):
        "fd464ba9f9893fafce026923427920b931133eb2d24a05deb799f9d32586be8f",
    ("discovery", "color", 0):
        "5c3b4d290f3b89bab530c9189f8d0867de646db67fcb516074f4d73043d8f9fc",
    ("discovery", "color", 1):
        "a7ba0b1ca268915ca9edd479fc80bd72f909e13b56355f0112fc96ab71b6ae85",
    ("calibration", "color", 0):
        "0da47a129d9adab022ad7ebd061e872f0141aa348dd5448630b9c4717c7fbaf9",
}


def _calibration_shortlist(kind: str) -> tuple[int, ...]:
    codes = [
        code for code in discovery_candidate_codes(kind)
        if CANDIDATES_BY_CODE[code].grid_dpi == (600, 600)
    ]
    return tuple(sorted(codes)[:4])


@pytest.mark.parametrize(
    ("stage", "kind", "copy_index"), sorted(_PAGE_DIGESTS)
)
def test_page_plan_digests_frozen(stage: str, kind: str, copy_index: int):
    codes = (
        None if stage == "discovery" else _calibration_shortlist(kind)
    )
    page = build_page(
        stage=stage, kind=kind, copy_index=copy_index,
        request_code=REQUEST_CODES["default"], candidate_codes=codes,
    )
    assert semantic_digest(page) == _PAGE_DIGESTS[(stage, kind, copy_index)]
