"""Compact current print-time report strip.

The characterization sheet has one current machine-report transport.  It
combines the static page identity needed to regenerate the stimulus with the
device state that can only be observed by the PostScript interpreter at print
time.  Static and dynamic fields share one integrity envelope but remain
separate dataclasses because interpreter readback is provenance, not physical
truth.

Transport geometry (black is one) is fixed:

* 160 payload bytes; CRC-16/CCITT-FALSE covers bytes ``0:158`` and is stored
  big-endian in bytes ``158:160``;
* four rows of 40 bytes;
* each byte is eight MSB-first bits followed by an even-parity bit;
* each row is ``1011`` sync, 40 encoded bytes, one encoded row-XOR byte, and
  three white pad modules;
* a solid border, quiet rows/columns, a black-first top clock and the opposed
  bottom clock produce a 380 by 10 module strip.

Payload bytes are current-only: ``0:4`` magic, ``4`` transport version,
``5:7`` stage/kind, ``7`` request code, ``8:10`` copy index, ``10`` explicit
candidate count, ``11`` reserved zero, ``12:20`` candidate slots,
``20:36`` the first 128 bits of
the layout SHA-256, ``36:40`` requested x/y DPI, ``40:42`` availability,
``42:46`` language level/color model/duplex/tumble, ``46:66`` default and
effective DPI/PageSize/ImagingBBox, ``66:70`` truncation and string lengths,
``70:72`` reserved zero, ``72:84`` revision and print nonce, ``84:158`` bounded
product/version/serial strings, and ``158:160`` CRC.

The scan decoder is registration-guided.  Callers supply fixed layout-space
strip reservations and the page affine; crops are rectified into canonical
orientation before local border/clock recovery.  No historical transport,
magic, layout, or parser is accepted.
"""

from __future__ import annotations

import math
import struct
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .geometry import (
    GeometryError,
    LAYOUT_DPI,
    OutOfRasterError,
    sample_layout_points,
)
from .model import (
    CANDIDATES_BY_CODE,
    Identity,
    KIND_CODES,
    KIND_NAMES,
    REQUEST_DPI,
    REQUEST_NAMES,
    STAGE_CODES,
    STAGE_NAMES,
    discovery_candidate_codes,
)
from .raster import RasterSource


REPORT_MAGIC = b"HCRP"
REPORT_VERSION = 1
REPORT_PAYLOAD_BYTES = 160
REPORT_CRC_OFFSET = 158

REPORT_DATA_ROWS = 4
REPORT_BYTES_PER_ROW = 40
REPORT_INTERIOR_MODULES = 376
REPORT_WIDTH_MODULES = 380
REPORT_HEIGHT_MODULES = 10
REPORT_BORDER_SEPARATION_MODULES = REPORT_HEIGHT_MODULES - 1
REPORT_CLOCK_SEPARATION_MODULES = REPORT_DATA_ROWS + 1
REPORT_ROW_SYNC = (1, 0, 1, 1)
REPORT_ROW_PAD_MODULES = 3
REPORT_SEARCH_MARGIN_LAYOUT_DOTS = 18.0

_CANDIDATE_SLOTS = 8
_PRODUCT_BYTES = 40
_VERSION_BYTES = 18
_SERIAL_BYTES = 16

_AV_LANGUAGE_LEVEL = 1 << 0
_AV_DEFAULT_RESOLUTION = 1 << 1
_AV_EFFECTIVE_RESOLUTION = 1 << 2
_AV_PAGE_SIZE = 1 << 3
_AV_IMAGING_BBOX = 1 << 4
_AV_DUPLEX = 1 << 5
_AV_TUMBLE = 1 << 6
_AV_COLOR_MODEL = 1 << 7
_AV_PRODUCT = 1 << 8
_AV_VERSION = 1 << 9
_AV_REVISION = 1 << 10
_AV_SERIAL = 1 << 11
_AV_PRINT_NONCE = 1 << 12
_KNOWN_AVAILABILITY = (1 << 13) - 1

_TRUNC_PRODUCT = 1 << 0
_TRUNC_VERSION = 1 << 1
_TRUNC_SERIAL = 1 << 2
_KNOWN_TRUNCATION = _TRUNC_PRODUCT | _TRUNC_VERSION | _TRUNC_SERIAL

# Live-field wire offsets: the single source for the Python encoder and the
# generated PostScript writer (postscript_field_lines).  The scan-side
# reader is pinned to the same numbers by encode/decode round-trip tests.
_OFF_AVAILABILITY = 40
_OFF_LANGUAGE_LEVEL = 42
_OFF_COLOR_MODEL = 43
_OFF_DUPLEX = 44
_OFF_TUMBLE = 45
_OFF_DEFAULT_RESOLUTION = 46
_OFF_EFFECTIVE_RESOLUTION = 50
_OFF_PAGE_SIZE = 54
_OFF_IMAGING_BBOX = 58
_OFF_TRUNCATION = 66
_OFF_LEN_PRODUCT = 67
_OFF_LEN_VERSION = 68
_OFF_LEN_SERIAL = 69
_OFF_REVISION = 72
_OFF_PRINT_NONCE = 76
# The PostScript writer fills the low 32 of the 64-bit big-endian nonce
# field; the template keeps bytes 76:80 zero.
_OFF_PRINT_NONCE_LOW32 = 80
_OFF_PRODUCT = 84
_OFF_VERSION = 124
_OFF_SERIAL = 142

_TRISTATE_TO_CODE = {None: 0, False: 1, True: 2}
_CODE_TO_TRISTATE = {value: key for key, value in _TRISTATE_TO_CODE.items()}

_COLOR_MODEL_TO_CODE = {
    None: 0,
    "DeviceGray": 1,
    "DeviceRGB": 2,
    "DeviceCMYK": 3,
    "DeviceN": 4,
}
_CODE_TO_COLOR_MODEL = {
    value: key for key, value in _COLOR_MODEL_TO_CODE.items()
}


def crc16_ccitt(data: bytes | bytearray | memoryview) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection/xorout)."""

    crc = 0xFFFF
    for value in bytes(data):
        crc ^= value << 8
        for _ in range(8):
            crc = (
                ((crc << 1) ^ 0x1021) & 0xFFFF
                if crc & 0x8000
                else (crc << 1) & 0xFFFF
            )
    return crc


def _pair(
    value: tuple[int, int] | Sequence[int] | None,
    *,
    name: str,
    maximum: int = 0xFFFF,
) -> tuple[int, int] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)) or len(value) != 2:
        raise ValueError(f"{name} must be an x/y pair")
    if any(
        isinstance(item, (bool, np.bool_))
        or not isinstance(item, (int, np.integer))
        for item in value
    ):
        raise ValueError(f"{name} values must be integers")
    pair = tuple(int(item) for item in value)
    if any(
        item < 0 or item > maximum
        for item in pair
    ):
        raise ValueError(
            f"{name} values must be integers in 0..{maximum}"
        )
    return pair  # type: ignore[return-value]


def _bbox(
    value: tuple[int, int, int, int] | Sequence[int] | None,
) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)) or len(value) != 4:
        raise ValueError("imaging_bbox must contain four integers")
    if any(
        isinstance(item, (bool, np.bool_))
        or not isinstance(item, (int, np.integer))
        for item in value
    ):
        raise ValueError("imaging_bbox values must be integers")
    result = tuple(int(item) for item in value)
    if any(
        item < -0x8000 or item > 0x7FFF
        for item in result
    ):
        raise ValueError("imaging_bbox values must fit signed int16")
    return result  # type: ignore[return-value]


def _text(value: str | None, *, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None")
    if any(ord(character) > 0xFF for character in value):
        raise ValueError(f"{name} must be representable as ISO-8859-1 bytes")
    return value


@dataclass(frozen=True)
class ReportIdentity:
    """The compact, honest wire projection of :class:`model.Identity`.

    The full discovery candidate set is schema-implied and the full SHA-256
    is represented by its first 128 bits.  Consequently a decoded strip does
    not pretend to reconstruct a full :class:`Identity`; ``matches`` verifies
    a regenerated full identity against exactly the facts present on paper.
    """

    stage: str
    kind: str
    copy_index: int
    request_code: int
    layout_digest_128: str
    candidate_codes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.stage not in STAGE_CODES:
            raise ValueError(f"unknown report stage {self.stage!r}")
        if self.kind not in KIND_CODES:
            raise ValueError(f"unknown report page kind {self.kind!r}")
        if (
            isinstance(self.copy_index, (bool, np.bool_))
            or not isinstance(self.copy_index, (int, np.integer))
            or not 0 <= int(self.copy_index) <= 0xFFFF
        ):
            raise ValueError("copy_index must fit uint16")
        object.__setattr__(self, "copy_index", int(self.copy_index))
        if (
            isinstance(self.request_code, (bool, np.bool_))
            or not isinstance(self.request_code, (int, np.integer))
            or self.request_code not in REQUEST_NAMES
        ):
            raise ValueError(f"unknown request code {self.request_code}")
        object.__setattr__(self, "request_code", int(self.request_code))
        if (
            not isinstance(self.layout_digest_128, str)
            or len(self.layout_digest_128) != 32
            or any(
                character not in "0123456789abcdef"
                for character in self.layout_digest_128
            )
        ):
            raise ValueError(
                "layout_digest_128 must be 32 lowercase hexadecimal digits"
            )

        codes = tuple(int(code) for code in self.candidate_codes)
        if codes != tuple(sorted(set(codes))):
            raise ValueError("candidate_codes must be sorted and unique")
        if any(code not in CANDIDATES_BY_CODE for code in codes):
            raise ValueError("candidate_codes contains an unknown code")
        if any(
            CANDIDATES_BY_CODE[code].page_kind != self.kind for code in codes
        ):
            raise ValueError("candidate_codes crosses page kind")
        if self.stage == "discovery":
            if codes:
                raise ValueError(
                    "discovery candidate set is implied and must not be encoded"
                )
        elif not 1 <= len(codes) <= _CANDIDATE_SLOTS:
            raise ValueError(
                "calibration carries between one and eight candidate codes"
            )
        object.__setattr__(self, "candidate_codes", codes)

    @classmethod
    def from_identity(cls, identity: Identity) -> ReportIdentity:
        """Project a current full page identity onto the HCAL-R1 wire facts."""

        if not isinstance(identity, Identity):
            raise TypeError("identity must be a current characterize Identity")
        return cls(
            stage=identity.stage,
            kind=identity.kind,
            copy_index=identity.copy_index,
            request_code=identity.request_code,
            layout_digest_128=identity.layout_digest[:32],
            candidate_codes=(
                () if identity.stage == "discovery"
                else identity.candidate_codes
            ),
        )

    def matches(self, identity: Identity) -> bool:
        """Whether a regenerated full identity agrees with every wire fact."""

        if not isinstance(identity, Identity):
            return False
        return (
            self.stage == identity.stage
            and self.kind == identity.kind
            and self.copy_index == identity.copy_index
            and self.request_code == identity.request_code
            and self.resolved_candidate_codes
            == tuple(int(code) for code in identity.candidate_codes)
            and identity.layout_digest.startswith(self.layout_digest_128)
        )

    @property
    def resolved_candidate_codes(self) -> tuple[int, ...]:
        if self.stage == "discovery":
            return discovery_candidate_codes(self.kind)
        return self.candidate_codes

    @property
    def request_dpi(self) -> tuple[int, int] | None:
        value = REQUEST_DPI[self.request_code]
        return None if value is None else tuple(int(item) for item in value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "kind": self.kind,
            "copy_index": int(self.copy_index),
            "request_code": int(self.request_code),
            "request": REQUEST_NAMES[self.request_code],
            "request_dpi": (
                None if self.request_dpi is None else list(self.request_dpi)
            ),
            "layout_digest_128": self.layout_digest_128,
            "candidate_codes_encoded": list(self.candidate_codes),
            "candidate_codes": list(self.resolved_candidate_codes),
        }


@dataclass(frozen=True)
class DeviceSelfReport:
    """Live interpreter readback; every field may be unavailable."""

    language_level: int | None = None
    default_resolution: tuple[int, int] | None = None
    effective_resolution: tuple[int, int] | None = None
    page_size_points: tuple[int, int] | None = None
    imaging_bbox: tuple[int, int, int, int] | None = None
    duplex: bool | None = None
    tumble: bool | None = None
    process_color_model: str | None = None
    product: str | None = None
    version: str | None = None
    revision: int | None = None
    serial: str | None = None
    print_nonce: int | None = None
    truncated_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.language_level is not None and (
            isinstance(self.language_level, (bool, np.bool_))
            or not isinstance(self.language_level, (int, np.integer))
            or not 1 <= int(self.language_level) <= 0xFF
        ):
            raise ValueError("language_level must be an integer in 1..255")
        if self.language_level is not None:
            object.__setattr__(
                self, "language_level", int(self.language_level)
            )
        object.__setattr__(
            self,
            "default_resolution",
            _pair(self.default_resolution, name="default_resolution"),
        )
        object.__setattr__(
            self,
            "effective_resolution",
            _pair(self.effective_resolution, name="effective_resolution"),
        )
        object.__setattr__(
            self,
            "page_size_points",
            _pair(self.page_size_points, name="page_size_points"),
        )
        object.__setattr__(self, "imaging_bbox", _bbox(self.imaging_bbox))
        if self.duplex is not None and not isinstance(
            self.duplex, (bool, np.bool_)
        ):
            raise TypeError("duplex must be bool or None")
        if self.tumble is not None and not isinstance(
            self.tumble, (bool, np.bool_)
        ):
            raise TypeError("tumble must be bool or None")
        if self.duplex is not None:
            object.__setattr__(self, "duplex", bool(self.duplex))
        if self.tumble is not None:
            object.__setattr__(self, "tumble", bool(self.tumble))
        if self.process_color_model not in _COLOR_MODEL_TO_CODE:
            raise ValueError(
                "process_color_model must be DeviceGray, DeviceRGB, "
                "DeviceCMYK, DeviceN, or None"
            )
        for name in ("product", "version", "serial"):
            object.__setattr__(
                self, name, _text(getattr(self, name), name=name)
            )
        if self.revision is not None and (
            isinstance(self.revision, (bool, np.bool_))
            or not isinstance(self.revision, (int, np.integer))
            or not -(1 << 31) <= int(self.revision) < (1 << 31)
        ):
            raise ValueError("revision must fit signed int32")
        if self.revision is not None:
            object.__setattr__(self, "revision", int(self.revision))
        if self.print_nonce is not None and (
            isinstance(self.print_nonce, (bool, np.bool_))
            or not isinstance(self.print_nonce, (int, np.integer))
            or not 0 <= int(self.print_nonce) < (1 << 64)
        ):
            raise ValueError("print_nonce must fit uint64")
        if self.print_nonce is not None:
            object.__setattr__(self, "print_nonce", int(self.print_nonce))
        truncated = tuple(str(value) for value in self.truncated_fields)
        if len(set(truncated)) != len(truncated) or any(
            value not in {"product", "version", "serial"}
            for value in truncated
        ):
            raise ValueError(
                "truncated_fields may contain product, version, and serial once"
            )
        if any(getattr(self, value) is None for value in truncated):
            raise ValueError("an unavailable string cannot be marked truncated")
        object.__setattr__(
            self,
            "truncated_fields",
            tuple(
                name for name in ("product", "version", "serial")
                if name in truncated
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "language_level": self.language_level,
            "default_resolution": (
                None
                if self.default_resolution is None
                else list(self.default_resolution)
            ),
            "effective_resolution": (
                None
                if self.effective_resolution is None
                else list(self.effective_resolution)
            ),
            "page_size_points": (
                None
                if self.page_size_points is None
                else list(self.page_size_points)
            ),
            "imaging_bbox": (
                None if self.imaging_bbox is None else list(self.imaging_bbox)
            ),
            "duplex": self.duplex,
            "tumble": self.tumble,
            "process_color_model": self.process_color_model,
            "product": self.product,
            "version": self.version,
            "revision": self.revision,
            "serial": self.serial,
            "print_nonce": self.print_nonce,
            "truncated_fields": list(self.truncated_fields),
        }


@dataclass(frozen=True)
class ReportPayload:
    identity: ReportIdentity
    device_readback: DeviceSelfReport


def _encode_string(
    value: str | None,
    capacity: int,
) -> tuple[bytes, bool]:
    if value is None:
        return b"", False
    encoded = value.encode("latin-1")
    return encoded[:capacity], len(encoded) > capacity


def encode_report_payload(
    identity: Identity,
    device_readback: DeviceSelfReport,
) -> bytes:
    """Encode one current full identity plus live device readback."""

    static = ReportIdentity.from_identity(identity)
    if not isinstance(device_readback, DeviceSelfReport):
        raise TypeError("device_readback must be a DeviceSelfReport")
    device = device_readback
    payload = bytearray(REPORT_PAYLOAD_BYTES)
    payload[0:4] = REPORT_MAGIC
    payload[4] = REPORT_VERSION
    payload[5] = STAGE_CODES[static.stage]
    payload[6] = KIND_CODES[static.kind]
    payload[7] = static.request_code
    struct.pack_into(">H", payload, 8, int(static.copy_index))
    if len(static.candidate_codes) > _CANDIDATE_SLOTS:
        raise ValueError("calibration carries at most eight candidate codes")
    payload[10] = len(static.candidate_codes)
    payload[11] = 0
    payload[12:20] = bytes(static.candidate_codes).ljust(_CANDIDATE_SLOTS, b"\0")
    payload[20:36] = bytes.fromhex(static.layout_digest_128)
    requested = static.request_dpi or (0, 0)
    struct.pack_into(">HH", payload, 36, *requested)

    availability = 0
    if device.language_level is not None:
        availability |= _AV_LANGUAGE_LEVEL
        payload[_OFF_LANGUAGE_LEVEL] = int(device.language_level)
    if device.default_resolution is not None:
        availability |= _AV_DEFAULT_RESOLUTION
        struct.pack_into(">HH", payload, _OFF_DEFAULT_RESOLUTION,
                         *device.default_resolution)
    if device.effective_resolution is not None:
        availability |= _AV_EFFECTIVE_RESOLUTION
        struct.pack_into(">HH", payload, _OFF_EFFECTIVE_RESOLUTION,
                         *device.effective_resolution)
    if device.page_size_points is not None:
        availability |= _AV_PAGE_SIZE
        struct.pack_into(">HH", payload, _OFF_PAGE_SIZE,
                         *device.page_size_points)
    if device.imaging_bbox is not None:
        availability |= _AV_IMAGING_BBOX
        struct.pack_into(">hhhh", payload, _OFF_IMAGING_BBOX,
                         *device.imaging_bbox)
    if device.duplex is not None:
        availability |= _AV_DUPLEX
    payload[_OFF_DUPLEX] = _TRISTATE_TO_CODE[device.duplex]
    if device.tumble is not None:
        availability |= _AV_TUMBLE
    payload[_OFF_TUMBLE] = _TRISTATE_TO_CODE[device.tumble]
    if device.process_color_model is not None:
        availability |= _AV_COLOR_MODEL
    payload[_OFF_COLOR_MODEL] = _COLOR_MODEL_TO_CODE[
        device.process_color_model
    ]

    product, product_truncated = _encode_string(
        device.product, _PRODUCT_BYTES
    )
    version, version_truncated = _encode_string(
        device.version, _VERSION_BYTES
    )
    serial, serial_truncated = _encode_string(device.serial, _SERIAL_BYTES)
    truncation = 0
    if device.product is not None:
        availability |= _AV_PRODUCT
    if product_truncated:
        truncation |= _TRUNC_PRODUCT
    if device.version is not None:
        availability |= _AV_VERSION
    if version_truncated:
        truncation |= _TRUNC_VERSION
    if device.serial is not None:
        availability |= _AV_SERIAL
    if serial_truncated:
        truncation |= _TRUNC_SERIAL
    for field_name, bit in (
        ("product", _TRUNC_PRODUCT),
        ("version", _TRUNC_VERSION),
        ("serial", _TRUNC_SERIAL),
    ):
        if field_name in device.truncated_fields:
            truncation |= bit
    if device.revision is not None:
        availability |= _AV_REVISION
        struct.pack_into(">i", payload, _OFF_REVISION, int(device.revision))
    if device.print_nonce is not None:
        availability |= _AV_PRINT_NONCE
        struct.pack_into(">Q", payload, _OFF_PRINT_NONCE,
                         int(device.print_nonce))

    struct.pack_into(">H", payload, _OFF_AVAILABILITY, availability)
    payload[_OFF_TRUNCATION] = truncation
    payload[_OFF_LEN_PRODUCT] = len(product)
    payload[_OFF_LEN_VERSION] = len(version)
    payload[_OFF_LEN_SERIAL] = len(serial)
    payload[70:72] = b"\0\0"
    payload[_OFF_PRODUCT:_OFF_VERSION] = product.ljust(_PRODUCT_BYTES, b"\0")
    payload[_OFF_VERSION:_OFF_SERIAL] = version.ljust(_VERSION_BYTES, b"\0")
    payload[_OFF_SERIAL:REPORT_CRC_OFFSET] = serial.ljust(
        _SERIAL_BYTES, b"\0"
    )

    crc = crc16_ccitt(payload[:REPORT_CRC_OFFSET])
    struct.pack_into(">H", payload, REPORT_CRC_OFFSET, crc)
    return bytes(payload)


def report_template(identity: Identity) -> bytes:
    """Static HCAL-R1 bytes; the guarded PostScript fills the live fields
    and recomputes the CRC in place (bytes 158:160 stay zero here)."""

    payload = bytearray(encode_report_payload(identity, DeviceSelfReport()))
    payload[REPORT_CRC_OFFSET:] = b"\x00\x00"
    return bytes(payload)


def postscript_field_lines() -> list[str]:
    """The live-field wiring of the printed HCAL-R1 encoder.

    Generated from the same offsets, availability bits, truncation bits,
    and slot capacities the Python encoder uses, so the printed record and
    ``encode_report_payload`` cannot drift apart field by field.  The
    device-fetch preamble (the *OK flags and fetched values these lines
    consume) stays in ``emit._report_postscript``; it contains no wire
    numbers.
    """

    return [
        f"LLOK {{ {_AV_LANGUAGE_LEVEL} SETAV "
        f"PAY {_OFF_LANGUAGE_LEVEL} LLV put }} if",
        f"RDOK {{ {_AV_DEFAULT_RESOLUTION} SETAV "
        f"RD {_OFF_DEFAULT_RESOLUTION} PUTPAIRAT }} if",
        f"REOK {{ {_AV_EFFECTIVE_RESOLUTION} SETAV "
        f"RE {_OFF_EFFECTIVE_RESOLUTION} PUTPAIRAT }} if",
        f"PSOK {{ {_AV_PAGE_SIZE} SETAV PSZ {_OFF_PAGE_SIZE} PUTPAIRAT }} if",
        f"IBOK {{ {_AV_IMAGING_BBOX} SETAV "
        f"IB {_OFF_IMAGING_BBOX} PUTQUADAT }} if",
        f"DUOK {{ {_AV_DUPLEX} SETAV PAY {_OFF_DUPLEX} DU put }} if",
        f"TUOK {{ {_AV_TUMBLE} SETAV PAY {_OFF_TUMBLE} TU put }} if",
        f"CMOK {{ {_AV_COLOR_MODEL} SETAV PAY {_OFF_COLOR_MODEL} CM put }} if",
        f"PROK {{ {_AV_PRODUCT} SETAV PRO {_OFF_LEN_PRODUCT} {_OFF_PRODUCT} "
        f"{_PRODUCT_BYTES} {_TRUNC_PRODUCT} PUTSLOT }} if",
        f"VERK {{ {_AV_VERSION} SETAV VER {_OFF_LEN_VERSION} {_OFF_VERSION} "
        f"{_VERSION_BYTES} {_TRUNC_VERSION} PUTSLOT }} if",
        f"RVOK {{ {_AV_REVISION} SETAV RV {_OFF_REVISION} PUT32AT }} if",
        f"SNOK {{ {_AV_SERIAL} SETAV SN {_OFF_LEN_SERIAL} {_OFF_SERIAL} "
        f"{_SERIAL_BYTES} {_TRUNC_SERIAL} PUTSLOT }} if",
        f"NONCEOK {{ {_AV_PRINT_NONCE} SETAV "
        f"NONCE {_OFF_PRINT_NONCE_LOW32} PUT32AT }} if",
        f"AV {_OFF_AVAILABILITY} PUT16AT PAY {_OFF_TRUNCATION} TR put",
    ]


def postscript_strip_lines() -> list[str]:
    """The strip raster drawer, generated from the module-geometry
    constants ``payload_to_modules`` and the scan decoder read."""

    clock_low = 2
    clock_high = clock_low + REPORT_CLOCK_SEPARATION_MODULES
    first_data_row = clock_high - 1
    sync = " ".join(f"{bit} PUTBIT" for bit in REPORT_ROW_SYNC)
    return [
        f"/W {REPORT_WIDTH_MODULES} def /H {REPORT_HEIGHT_MODULES} def "
        f"/WI {REPORT_INTERIOR_MODULES} def /NB {REPORT_BYTES_PER_ROW} def "
        f"/NR {REPORT_DATA_ROWS} def",
        "/PUTBIT { 1 eq { COL ROW 1 1 rectfill } if",
        "  /COL COL 1 add def } bind def",
        "/PUTBYTE { /B exch def /PARITY 0 def",
        "  7 -1 0 { /I exch def B I neg bitshift 1 and",
        "    dup PARITY xor /PARITY exch def PUTBIT } for",
        "  PARITY PUTBIT } bind def",
        "/STRIP { /SY exch def /SX exch def gsave",
        "  SX SY translate 0 0 0 1 setcmykcolor",
        "  0 0 W 1 rectfill 0 H 1 sub W 1 rectfill",
        "  0 0 1 H rectfill W 1 sub 0 1 H rectfill",
        f"  0 2 WI 1 sub {{ 2 add {clock_high} 1 1 rectfill }} for",
        f"  1 2 WI 1 sub {{ 2 add {clock_low} 1 1 rectfill }} for",
        "  0 1 NR 1 sub { /R exch def"
        f" /ROW {first_data_row} R sub def /COL 2 def",
        f"    {sync} /RX 0 def",
        "    0 1 NB 1 sub { /I exch def PAY R NB mul I add get",
        "      dup RX xor /RX exch def PUTBYTE } for",
        "    RX PUTBYTE } for grestore } bind def",
    ]


def _decode_string(
    payload: bytes,
    *,
    offset: int,
    capacity: int,
    length: int,
    available: bool,
    name: str,
) -> str | None:
    if length > capacity:
        raise ValueError(f"{name} length exceeds its report field")
    field = payload[offset:offset + capacity]
    if any(field[length:]):
        raise ValueError(f"{name} field has nonzero bytes after its length")
    if not available:
        if length or any(field):
            raise ValueError(f"{name} bytes present without availability bit")
        return None
    return field[:length].decode("latin-1")


def decode_report_payload(payload: bytes | bytearray | memoryview) -> ReportPayload:
    """Decode and strictly validate one current 160-byte report payload."""

    raw = bytes(payload)
    if len(raw) != REPORT_PAYLOAD_BYTES:
        raise ValueError(
            f"report payload must be exactly {REPORT_PAYLOAD_BYTES} bytes"
        )
    expected_crc = struct.unpack_from(">H", raw, REPORT_CRC_OFFSET)[0]
    if crc16_ccitt(raw[:REPORT_CRC_OFFSET]) != expected_crc:
        raise ValueError("report payload CRC mismatch")
    if raw[0:4] != REPORT_MAGIC or raw[4] != REPORT_VERSION:
        raise ValueError("report payload magic/version mismatch")
    if raw[5] not in STAGE_NAMES or raw[6] not in KIND_NAMES:
        raise ValueError("report payload stage/kind code invalid")
    if raw[7] not in REQUEST_NAMES:
        raise ValueError("report payload request code invalid")
    if raw[11] != 0 or raw[70:72] != b"\0\0":
        raise ValueError("report payload reserved fields are nonzero")

    stage, kind = STAGE_NAMES[raw[5]], KIND_NAMES[raw[6]]
    count = raw[10]
    if count > _CANDIDATE_SLOTS:
        raise ValueError("report candidate count exceeds eight")
    slots = raw[12:20]
    if any(slots[count:]):
        raise ValueError("unused report candidate slots are nonzero")
    candidate_codes = tuple(int(code) for code in slots[:count])
    request_code = raw[7]
    requested = struct.unpack_from(">HH", raw, 36)
    expected_requested = REQUEST_DPI[request_code] or (0, 0)
    if requested != tuple(expected_requested):
        raise ValueError("report request code and requested DPI disagree")

    identity = ReportIdentity(
        stage=stage,
        kind=kind,
        copy_index=struct.unpack_from(">H", raw, 8)[0],
        request_code=request_code,
        layout_digest_128=raw[20:36].hex(),
        candidate_codes=candidate_codes,
    )

    availability = struct.unpack_from(">H", raw, 40)[0]
    if availability & ~_KNOWN_AVAILABILITY:
        raise ValueError("report availability has reserved bits set")
    truncation = raw[66]
    if truncation & ~_KNOWN_TRUNCATION:
        raise ValueError("report truncation has reserved bits set")
    if raw[43] not in _CODE_TO_COLOR_MODEL:
        raise ValueError("report process color model code invalid")
    if raw[44] not in _CODE_TO_TRISTATE or raw[45] not in _CODE_TO_TRISTATE:
        raise ValueError("report duplex/tumble code invalid")

    def available(bit: int) -> bool:
        return bool(availability & bit)

    if bool(raw[42]) != available(_AV_LANGUAGE_LEVEL):
        raise ValueError("report language-level availability disagrees")
    if bool(raw[43]) != available(_AV_COLOR_MODEL):
        raise ValueError("report color-model availability disagrees")
    if (raw[44] != 0) != available(_AV_DUPLEX):
        raise ValueError("report duplex availability disagrees")
    if (raw[45] != 0) != available(_AV_TUMBLE):
        raise ValueError("report tumble availability disagrees")

    def unpack_pair(offset: int, bit: int) -> tuple[int, int] | None:
        value = struct.unpack_from(">HH", raw, offset)
        if available(bit):
            return value
        if value != (0, 0):
            raise ValueError("unavailable report pair is nonzero")
        return None

    bbox_values = struct.unpack_from(">hhhh", raw, 58)
    if available(_AV_IMAGING_BBOX):
        imaging_bbox: tuple[int, int, int, int] | None = bbox_values
    else:
        if bbox_values != (0, 0, 0, 0):
            raise ValueError("unavailable report imaging bbox is nonzero")
        imaging_bbox = None

    revision_value = struct.unpack_from(">i", raw, 72)[0]
    if not available(_AV_REVISION) and revision_value != 0:
        raise ValueError("unavailable report revision is nonzero")
    nonce_value = struct.unpack_from(">Q", raw, 76)[0]
    if not available(_AV_PRINT_NONCE) and nonce_value != 0:
        raise ValueError("unavailable report print nonce is nonzero")

    product = _decode_string(
        raw,
        offset=84,
        capacity=_PRODUCT_BYTES,
        length=raw[67],
        available=available(_AV_PRODUCT),
        name="product",
    )
    version = _decode_string(
        raw,
        offset=124,
        capacity=_VERSION_BYTES,
        length=raw[68],
        available=available(_AV_VERSION),
        name="version",
    )
    serial = _decode_string(
        raw,
        offset=142,
        capacity=_SERIAL_BYTES,
        length=raw[69],
        available=available(_AV_SERIAL),
        name="serial",
    )

    # Truncation is a provenance fact rather than a decode error.  The
    # bounded string itself remains useful and is returned verbatim.
    device = DeviceSelfReport(
        language_level=(raw[42] if available(_AV_LANGUAGE_LEVEL) else None),
        default_resolution=unpack_pair(46, _AV_DEFAULT_RESOLUTION),
        effective_resolution=unpack_pair(50, _AV_EFFECTIVE_RESOLUTION),
        page_size_points=unpack_pair(54, _AV_PAGE_SIZE),
        imaging_bbox=imaging_bbox,
        duplex=(
            _CODE_TO_TRISTATE[raw[44]]
            if available(_AV_DUPLEX)
            else None
        ),
        tumble=(
            _CODE_TO_TRISTATE[raw[45]]
            if available(_AV_TUMBLE)
            else None
        ),
        process_color_model=(
            _CODE_TO_COLOR_MODEL[raw[43]]
            if available(_AV_COLOR_MODEL)
            else None
        ),
        product=product,
        version=version,
        revision=(revision_value if available(_AV_REVISION) else None),
        serial=serial,
        print_nonce=(nonce_value if available(_AV_PRINT_NONCE) else None),
        truncated_fields=tuple(
            name
            for name, bit in (
                ("product", _TRUNC_PRODUCT),
                ("version", _TRUNC_VERSION),
                ("serial", _TRUNC_SERIAL),
            )
            if truncation & bit
        ),
    )
    return ReportPayload(identity=identity, device_readback=device)


def _byte_modules(value: int) -> np.ndarray:
    bits = np.asarray(
        [(value >> shift) & 1 for shift in range(7, -1, -1)],
        dtype=np.uint8,
    )
    parity = int(bits.sum()) & 1
    return np.concatenate((bits, np.asarray([parity], dtype=np.uint8)))


def payload_to_modules(
    payload: bytes | bytearray | memoryview,
) -> np.ndarray:
    """Render a report payload into the normative 10x380 black-is-one matrix."""

    raw = bytes(payload)
    if len(raw) != REPORT_PAYLOAD_BYTES:
        raise ValueError(
            f"report payload must be exactly {REPORT_PAYLOAD_BYTES} bytes"
        )
    modules = np.zeros(
        (REPORT_HEIGHT_MODULES, REPORT_WIDTH_MODULES), dtype=np.uint8
    )
    modules[0, :] = 1
    modules[-1, :] = 1
    modules[:, 0] = 1
    modules[:, -1] = 1
    interior = modules[2:-2, 2:-2]
    interior[0, 0::2] = 1
    interior[-1, 1::2] = 1
    for row in range(REPORT_DATA_ROWS):
        start = row * REPORT_BYTES_PER_ROW
        values = raw[start:start + REPORT_BYTES_PER_ROW]
        row_xor = 0
        bits = list(REPORT_ROW_SYNC)
        for value in values:
            row_xor ^= value
            bits.extend(int(bit) for bit in _byte_modules(value))
        bits.extend(int(bit) for bit in _byte_modules(row_xor))
        bits.extend([0] * REPORT_ROW_PAD_MODULES)
        if len(bits) != REPORT_INTERIOR_MODULES:
            raise AssertionError("report row module arithmetic drifted")
        interior[1 + row, :] = np.asarray(bits, dtype=np.uint8)
    return modules



__all__ = [
    "DeviceSelfReport",
    "REPORT_BORDER_SEPARATION_MODULES",
    "REPORT_BYTES_PER_ROW",
    "REPORT_CRC_OFFSET",
    "REPORT_DATA_ROWS",
    "REPORT_HEIGHT_MODULES",
    "REPORT_INTERIOR_MODULES",
    "REPORT_MAGIC",
    "REPORT_PAYLOAD_BYTES",
    "REPORT_SEARCH_MARGIN_LAYOUT_DOTS",
    "REPORT_VERSION",
    "REPORT_WIDTH_MODULES",
    "ReportPayload",
    "ReportIdentity",
    "crc16_ccitt",
    "decode_report_payload",
    "encode_report_payload",
    "payload_to_modules",
    "postscript_field_lines",
    "postscript_strip_lines",
    "report_template",
]
