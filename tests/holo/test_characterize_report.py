from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from holo.characterize.model import Identity, discovery_candidate_codes
from holo.characterize.raster import RasterSource
from holo.characterize.report import (
    REPORT_BYTES_PER_ROW,
    REPORT_HEIGHT_MODULES,
    REPORT_PAYLOAD_BYTES,
    REPORT_WIDTH_MODULES,
    DeviceSelfReport,
    decode_report_payload,
    encode_report_payload,
    payload_to_modules,
)
from holo.characterize.report_strips import (
    ReportStripObservation,
    ReportStripRegion,
    decode_report_image,
    decode_report_strips,
    normalize_report_strips,
    report_strip_consensus,
)


def _report(
    *,
    stage: str = "discovery",
    kind: str = "bw",
    candidate_codes: tuple[int, ...] = (),
    nonce: int = 0x0123456789ABCDEF,
) -> tuple[Identity, DeviceSelfReport]:
    resolved_codes = (
        discovery_candidate_codes(kind)
        if stage == "discovery"
        else candidate_codes
    )
    return (
        Identity(
            stage=stage,
            kind=kind,
            copy_index=37,
            request_code=2,
            candidate_codes=resolved_codes,
            layout_digest=bytes(range(32)).hex(),
        ),
        DeviceSelfReport(
            language_level=3,
            default_resolution=(600, 600),
            effective_resolution=(600, 600),
            page_size_points=(595, 842),
            imaging_bbox=(-1, 0, 594, 841),
            duplex=False,
            tumble=True,
            process_color_model="DeviceRGB",
            product="HP Color LaserJet MFP M281fdw",
            version="3017",
            revision=1,
            serial="-1",
            print_nonce=nonce,
        ),
    )


def test_current_report_payload_round_trip_and_crc() -> None:
    identity, device = _report()

    payload = encode_report_payload(identity, device)

    assert len(payload) == REPORT_PAYLOAD_BYTES
    decoded = decode_report_payload(payload)
    assert decoded.identity.matches(identity)
    assert decoded.device_readback == device
    assert (
        decoded.identity.resolved_candidate_codes
        == discovery_candidate_codes("bw")
    )

    damaged = bytearray(payload)
    damaged[91] ^= 0x01
    with pytest.raises(ValueError, match="CRC mismatch"):
        decode_report_payload(damaged)


def test_calibration_encodes_only_its_explicit_candidate_codes() -> None:
    identity, device = _report(
        stage="calibration",
        candidate_codes=(1, 3, 7, 10, 20, 24, 30, 34),
    )

    decoded = decode_report_payload(encode_report_payload(identity, device))

    assert decoded.identity.matches(identity)
    assert decoded.device_readback == device
    assert decoded.identity.resolved_candidate_codes == identity.candidate_codes
    with pytest.raises(ValueError, match="one to eight"):
        dataclasses.replace(identity, candidate_codes=())
    with pytest.raises(ValueError, match="complete"):
        dataclasses.replace(
            identity,
            stage="discovery",
            candidate_codes=(1,),
        )


def test_bounded_strings_report_truncation_without_losing_integrity() -> None:
    identity, device = _report()
    device = dataclasses.replace(
        device,
        product="P" * 80,
        version="V" * 40,
        serial="S" * 30,
    )

    decoded = decode_report_payload(encode_report_payload(identity, device))

    assert decoded.device_readback.product == "P" * 40
    assert decoded.device_readback.version == "V" * 18
    assert decoded.device_readback.serial == "S" * 16
    assert decoded.device_readback.truncated_fields == (
        "product",
        "version",
        "serial",
    )

    latin_device = dataclasses.replace(device, product="éäöûçî")
    assert decode_report_payload(
        encode_report_payload(identity, latin_device)
    ).device_readback.product == "éäöûçî"
    with pytest.raises(ValueError, match="ISO-8859-1"):
        dataclasses.replace(device, product="printer \N{SNOWMAN}")
    with pytest.raises(ValueError, match="signed int32"):
        dataclasses.replace(device, revision=1.5)


def test_module_geometry_and_clock_decoder_round_trip() -> None:
    identity, device = _report()
    payload = encode_report_payload(identity, device)

    modules = payload_to_modules(payload)

    assert modules.shape == (
        REPORT_HEIGHT_MODULES,
        REPORT_WIDTH_MODULES,
    )
    assert np.all(modules[0] == 1)
    assert np.all(modules[-1] == 1)
    assert np.all(modules[:, 0] == 1)
    assert np.all(modules[:, -1] == 1)
    assert np.array_equal(
        modules[2, 2:-2], 1 - modules[-3, 2:-2]
    )
    image = np.repeat(
        np.repeat(1 - modules, 6, axis=0), 6, axis=1
    ).astype(np.float32)

    observations = decode_report_image(image)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.status == "ok"
    assert observation.report is not None
    assert observation.report.identity.matches(identity)
    assert observation.report.device_readback == device
    assert observation.clock_score == 1.0
    assert observation.sync_errors == 0
    assert observation.parity_errors == 0
    assert observation.row_xor_errors == 0
    assert observation.module_px == pytest.approx((6.0, 6.0))

    reversed_observations = decode_report_image(image[::-1, ::-1])
    assert len(reversed_observations) == 1
    assert reversed_observations[0].status == "ok"
    assert reversed_observations[0].rotated_180 is True


@pytest.mark.parametrize("transform", ("identity", "rotate_180", "rotate_90"))
def test_registration_guided_decoder_rectifies_page_orientation(
    transform: str,
) -> None:
    identity, device = _report()
    modules = payload_to_modules(encode_report_payload(identity, device))
    strip = np.repeat(
        np.repeat(255 * (1 - modules), 6, axis=0), 6, axis=1
    ).astype(np.uint8)
    raw = np.full((320, 2600), 255, dtype=np.uint8)
    x0, y0 = 120, 90
    raw[y0:y0 + strip.shape[0], x0:x0 + strip.shape[1]] = strip
    region = ReportStripRegion(
        placement_index=4,
        x_layout_dots=x0,
        y_layout_dots=y0,
        w_layout_dots=strip.shape[1],
        h_layout_dots=strip.shape[0],
    )
    if transform == "identity":
        capture = raw
        affine = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    elif transform == "rotate_180":
        capture = raw[::-1, ::-1].copy()
        affine = np.asarray(
            [[-1.0, 0.0, raw.shape[1] - 1], [0.0, -1.0, raw.shape[0] - 1]]
        )
    else:
        capture = np.rot90(raw, 1).copy()
        affine = np.asarray(
            [[0.0, 1.0, 0.0], [-1.0, 0.0, raw.shape[1] - 1]]
        )

    observations = decode_report_strips(
        RasterSource(capture),
        affine,
        [region],
    )

    assert len(observations) == 1
    assert observations[0].status == "ok"
    assert observations[0].placement_index == 4
    assert observations[0].report is not None
    assert observations[0].report.identity.matches(identity)
    assert observations[0].report.device_readback == device


@pytest.mark.parametrize(
    ("offset_x", "offset_y"),
    ((-12, 0), (12, 0), (0, -12), (0, 12), (10, -10)),
)
def test_registration_guided_decoder_searches_around_nominal_region(
    offset_x: int,
    offset_y: int,
) -> None:
    identity, device = _report()
    modules = payload_to_modules(encode_report_payload(identity, device))
    strip = np.repeat(
        np.repeat(255 * (1 - modules), 6, axis=0), 6, axis=1
    ).astype(np.uint8)
    raw = np.full((320, 2600), 255, dtype=np.uint8)
    x0, y0 = 120, 90
    raw[y0:y0 + strip.shape[0], x0:x0 + strip.shape[1]] = strip
    region = ReportStripRegion(
        placement_index=0,
        x_layout_dots=x0 + offset_x,
        y_layout_dots=y0 + offset_y,
        w_layout_dots=strip.shape[1],
        h_layout_dots=strip.shape[0],
    )

    observations = decode_report_strips(
        RasterSource(raw),
        np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        [region],
    )

    assert len(observations) == 1
    assert observations[0].status == "ok"
    assert observations[0].report is not None
    assert observations[0].report.identity.matches(identity)
    assert observations[0].report.device_readback == device


def test_consensus_accepts_one_or_equal_copies_and_refuses_disagreement() -> None:
    first_identity, first_device = _report(nonce=1)
    second_identity, second_device = _report(nonce=2)
    first_payload = encode_report_payload(first_identity, first_device)
    second_payload = encode_report_payload(second_identity, second_device)
    first = decode_report_payload(first_payload)
    second = decode_report_payload(second_payload)
    first_observation = ReportStripObservation(
        placement_index=0,
        status="ok",
        payload=first_payload,
        report=first,
        crc_ok=True,
        magic_ok=True,
    )
    same_observation = dataclasses.replace(
        first_observation, placement_index=1
    )
    different_observation = ReportStripObservation(
        placement_index=1,
        status="ok",
        payload=second_payload,
        report=second,
        crc_ok=True,
        magic_ok=True,
    )

    report, diagnostics = report_strip_consensus([first_observation])
    assert report == first
    assert diagnostics["n_valid"] == 1
    report, diagnostics = report_strip_consensus(
        [first_observation, same_observation]
    )
    assert report == first
    assert diagnostics["n_valid"] == 2
    report, diagnostics = report_strip_consensus(
        [first_observation, different_observation]
    )
    assert report is None
    assert diagnostics["status"] == "report_strip_disagreement"
    inconsistent = dataclasses.replace(first_observation, crc_ok=False)
    report, diagnostics = report_strip_consensus([inconsistent])
    assert report is None
    assert diagnostics["status"] == "no_valid_report_strip"

    normalized = normalize_report_strips(
        [first_observation, same_observation]
    )
    assert normalized["identity"]["layout_digest_128"] == bytes(
        range(16)
    ).hex()
    assert normalized["device_readback"]["print_nonce"] == 1
    assert normalized["consensus"]["status"] == "ok"
    assert normalized["strip_diagnostics"][0]["status"] == "ok"
    assert "report" not in normalized["strip_diagnostics"][0]
    assert "payload_hex" not in normalized["strip_diagnostics"][0]


_STRIP_SCALE = 12
_MARGIN = 0.05


def _strip_image(modules: np.ndarray) -> np.ndarray:
    return np.repeat(
        np.repeat(1.0 - modules, _STRIP_SCALE, axis=0),
        _STRIP_SCALE,
        axis=1,
    ).astype(np.float32)


def _paint_module(
    image: np.ndarray,
    data_row: int,
    column: int,
    value: float,
) -> None:
    """Overwrite one data-row module cell of a rendered strip."""

    y = (3 + data_row) * _STRIP_SCALE
    x = (2 + column) * _STRIP_SCALE
    image[y:y + _STRIP_SCALE, x:x + _STRIP_SCALE] = value


def _flip_module_marginally(
    image: np.ndarray,
    modules: np.ndarray,
    data_row: int,
    column: int,
    margin: float,
) -> None:
    """Push one module just past the slicer, the way channel noise does.

    Repair spends reliability, so a test error has to be the row's least
    reliable module rather than a confident wrong reading.
    """

    dark = modules[3 + data_row, 2 + column] == 0
    _paint_module(
        image, data_row, column, 0.5 - margin if dark else 0.5 + margin
    )


def test_demodulation_reads_module_centres_not_whole_cells() -> None:
    """Cell edges may carry a neighbour's ink; cell centres may not.

    Under the frozen hp-m281-flatbed channel the dominant scan-side error was
    a one-module white gap between two black modules read as black, at a rate
    of 0.53-0.76.  An aperture spanning most of the cell integrates exactly
    that encroachment, so the detector reads a narrow window at the centre.
    This caricature keeps the middle third of every cell truthful and gives
    the flanking thirds their horizontal neighbours' ink.  Only the four data
    rows are encroached, so border, clock and quiet-zone localization stay
    clean and the property under test is the aperture width alone.
    """

    identity, device = _report()
    payload = encode_report_payload(identity, device)
    modules = payload_to_modules(payload)

    encroached = np.maximum(
        modules,
        np.maximum(
            np.roll(modules, 1, axis=1), np.roll(modules, -1, axis=1)
        ),
    )
    flank = np.ones(_STRIP_SCALE, dtype=bool)
    flank[_STRIP_SCALE // 3:_STRIP_SCALE - _STRIP_SCALE // 3] = False
    encroach = np.zeros(modules.shape, dtype=bool)
    encroach[3:7] = True

    blended = np.where(
        np.repeat(
            np.repeat(encroach, _STRIP_SCALE, axis=0), _STRIP_SCALE, axis=1
        )
        & np.tile(flank, modules.shape[1])[None, :],
        np.repeat(
            np.repeat(encroached, _STRIP_SCALE, axis=0), _STRIP_SCALE, axis=1
        ),
        np.repeat(
            np.repeat(modules, _STRIP_SCALE, axis=0), _STRIP_SCALE, axis=1
        ),
    )

    observations = decode_report_image(
        (1.0 - blended).astype(np.float32)
    )

    assert len(observations) == 1
    assert observations[0].status == "ok"
    assert observations[0].payload == payload
    assert observations[0].parity_errors == 0
    assert observations[0].row_xor_errors == 0


def test_parity_repairs_the_least_reliable_module_of_a_byte() -> None:
    identity, device = _report()
    payload = encode_report_payload(identity, device)
    modules = payload_to_modules(payload)
    image = _strip_image(modules)

    _flip_module_marginally(image, modules, 1, 4 + 9 * 3 + 5, _MARGIN)

    observations = decode_report_image(image)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.status == "ok"
    assert observation.payload == payload
    assert observation.parity_errors == 1
    assert observation.row_xor_errors == 0
    assert observation.xor_repairs == 0


def test_row_xor_repairs_a_byte_whose_parity_survives() -> None:
    identity, device = _report()
    payload = encode_report_payload(identity, device)
    modules = payload_to_modules(payload)
    image = _strip_image(modules)

    _flip_module_marginally(image, modules, 1, 4 + 9 * 7 + 1, _MARGIN)
    _flip_module_marginally(image, modules, 1, 4 + 9 * 7 + 6, _MARGIN - 0.01)

    observations = decode_report_image(image)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.status == "ok"
    assert observation.payload == payload
    assert observation.parity_errors == 0
    assert observation.row_xor_errors == 1
    assert observation.xor_repairs == 1


def test_repairs_do_not_rescue_a_heavily_damaged_strip() -> None:
    """Repair raises tolerance; the CRC still decides acceptance."""

    identity, device = _report()
    payload = encode_report_payload(identity, device)
    image = _strip_image(payload_to_modules(payload))
    rng = np.random.default_rng(3)
    for _ in range(80):
        _paint_module(
            image,
            int(rng.integers(0, 4)),
            int(rng.integers(4, 4 + 9 * REPORT_BYTES_PER_ROW)),
            float(rng.choice([0.02, 0.98])),
        )

    observations = decode_report_image(image)

    assert observations
    for observation in observations:
        assert observation.status != "ok"
        assert not observation.crc_ok
        assert observation.report is None
        assert observation.payload != payload

    report, consensus = report_strip_consensus(observations)
    assert report is None
    assert consensus["status"] == "no_valid_report_strip"
