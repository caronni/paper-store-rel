"""Scan-side HCAL-R1 strip recovery: bars, clocks, demodulation, consensus.

The wire schema (record bytes, constants, encoder/decoder) lives in
``holo.characterize.report``; this module owns everything that reads strips
off a registered scan raster — bar finding, clock recovery, the Gaussian
cell-centre demodulator with its parity/XOR repair stage, and the
two-strip consensus the analyzer's hard gate consumes.
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .diagnostics import luma709
from .geometry import (
    GeometryError,
    LAYOUT_DPI,
    OutOfRasterError,
    sample_layout_points,
)
from .raster import RasterSource
from .report import (
    REPORT_BORDER_SEPARATION_MODULES,
    REPORT_CRC_OFFSET,
    REPORT_MAGIC,
    REPORT_VERSION,
    crc16_ccitt,
    REPORT_BYTES_PER_ROW,
    REPORT_CLOCK_SEPARATION_MODULES,
    REPORT_DATA_ROWS,
    REPORT_HEIGHT_MODULES,
    REPORT_INTERIOR_MODULES,
    REPORT_PAYLOAD_BYTES,
    REPORT_ROW_PAD_MODULES,
    REPORT_ROW_SYNC,
    REPORT_SEARCH_MARGIN_LAYOUT_DOTS,
    REPORT_WIDTH_MODULES,
    ReportPayload,
    decode_report_payload,
)


# Scan-side demodulation.  A module cell is six layout dots, so an aperture
# spanning most of the cell integrates a blurred neighbour's ink and reads a
# one-module white gap as black.  The detector instead reads the cell centre
# through a narrow Gaussian window, sub-pixel so the aperture is the same
# fraction of a cell at every working DPI, and keeps each module's distance
# to the slicing threshold as the reliability that the repair stage spends.
_APERTURE_SIGMA_MODULES = 0.06
_APERTURE_TAPS = 5


@dataclass(frozen=True)
class ReportStripRegion:
    """A fixed layout-space reservation used to locate one report strip."""

    placement_index: int
    x_layout_dots: float
    y_layout_dots: float
    w_layout_dots: float
    h_layout_dots: float

    def __post_init__(self) -> None:
        values = (
            self.x_layout_dots,
            self.y_layout_dots,
            self.w_layout_dots,
            self.h_layout_dots,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise GeometryError("report-strip region must be finite")
        if self.w_layout_dots <= 0 or self.h_layout_dots <= 0:
            raise GeometryError("report-strip region dimensions must be positive")


@dataclass(frozen=True)
class ReportStripObservation:
    """One located strip candidate or a structured location refusal."""

    placement_index: int | None
    status: str
    payload: bytes | None = None
    report: ReportPayload | None = None
    crc_ok: bool = False
    magic_ok: bool = False
    clock_score: float | None = None
    module_px: tuple[float, float] | None = None
    skew_deg: float | None = None
    sync_errors: int | None = None
    parity_errors: int | None = None
    row_xor_errors: int | None = None
    xor_repairs: int | None = None
    rotated_180: bool = False
    error: str | None = None

    def diagnostics_dict(self) -> dict[str, Any]:
        """Stable per-copy evidence without duplicating the decoded report."""

        return {
            "placement_index": self.placement_index,
            "status": self.status,
            "crc_ok": self.crc_ok,
            "magic_ok": self.magic_ok,
            "clock_score": self.clock_score,
            "module_px": (
                None if self.module_px is None else list(self.module_px)
            ),
            "skew_deg": self.skew_deg,
            "sync_errors": self.sync_errors,
            "parity_errors": self.parity_errors,
            "row_xor_errors": self.row_xor_errors,
            "xor_repairs": self.xor_repairs,
            "rotated_180": self.rotated_180,
            "error": self.error,
        }


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    changes = np.diff(
        np.concatenate(([0], mask.astype(np.int8, copy=False), [0]))
    )
    return list(
        zip(
            np.flatnonzero(changes == 1).tolist(),
            np.flatnonzero(changes == -1).tolist(),
        )
    )


def _find_bars(dark: np.ndarray, module_guess: float) -> list[dict[str, float]]:
    """Find long solid borders as fitted lines, not single-row runs."""

    height, width = dark.shape
    band_width = max(8, width // 64)
    n_bands = width // band_width
    if n_bands < 8:
        return []
    band_fill = dark[:, : n_bands * band_width].reshape(
        height, n_bands, band_width
    ).mean(axis=2)
    detections: list[tuple[float, float, float, int]] = []
    for band in range(n_bands):
        for start, end in _runs(band_fill[:, band] >= 0.95):
            run_height = end - start
            if 0.35 * module_guess <= run_height <= 3.5 * module_guess:
                detections.append(
                    (
                        (band + 0.5) * band_width,
                        (start + end) / 2.0,
                        float(run_height),
                        band,
                    )
                )

    parent = list(range(len(detections)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left in range(len(detections)):
        for right in range(left + 1, len(detections)):
            if abs(detections[right][3] - detections[left][3]) > 3:
                continue
            dx = abs(detections[right][0] - detections[left][0])
            if dx == 0:
                continue
            if (
                abs(detections[right][1] - detections[left][1])
                <= 0.025 * dx + 0.6 * module_guess
            ):
                root_left, root_right = find(left), find(right)
                if root_left != root_right:
                    parent[root_right] = root_left

    clusters: dict[int, list[int]] = {}
    for index in range(len(detections)):
        clusters.setdefault(find(index), []).append(index)

    bars: list[dict[str, float]] = []
    all_x = np.arange(width)
    for indices in clusters.values():
        xs = np.asarray([detections[index][0] for index in indices])
        ys = np.asarray([detections[index][1] for index in indices])
        heights = np.asarray([detections[index][2] for index in indices])
        bands = sorted({detections[index][3] for index in indices})
        if xs.size < 2 or xs.max() - xs.min() < 0.55 * width:
            continue
        if len(bands) < 0.5 * (bands[-1] - bands[0] + 1):
            continue
        fit = np.polyfit(xs, ys, 1)
        keep = np.abs(ys - np.polyval(fit, xs)) <= 0.6 * module_guess
        if keep.sum() >= 8:
            fit = np.polyfit(xs[keep], ys[keep], 1)
        half_window = max(1, int(round(0.35 * float(np.median(heights)))))
        rows = np.clip(
            np.round(np.polyval(fit, all_x)).astype(int)[None, :]
            + np.arange(-half_window, half_window + 1)[:, None],
            0,
            height - 1,
        )
        column_fill = dark[rows, all_x[None, :]].mean(axis=0)
        runs = _runs(column_fill > 0.6)
        if not runs:
            continue
        x0, x1 = max(runs, key=lambda pair: pair[1] - pair[0])
        if x1 - x0 < 0.55 * width:
            continue
        bars.append(
            {
                "slope": float(fit[0]),
                "intercept": float(fit[1]),
                "x0": float(x0),
                "x1": float(x1),
                "height": float(np.median(heights)),
            }
        )
    bars.sort(key=lambda item: item["intercept"])
    return bars


def _bar_y(
    bar: Mapping[str, float],
    x: np.ndarray | float,
) -> np.ndarray | float:
    return bar["intercept"] + bar["slope"] * x


def _pair_bars(
    bars: Sequence[Mapping[str, float]],
    image_width: int,
) -> list[tuple[Mapping[str, float], Mapping[str, float]]]:
    pairs = []
    for top_index in range(len(bars)):
        for bottom_index in range(top_index + 1, len(bars)):
            top, bottom = bars[top_index], bars[bottom_index]
            module_x = (
                (top["x1"] - top["x0"]) + (bottom["x1"] - bottom["x0"])
            ) / (2.0 * REPORT_WIDTH_MODULES)
            if module_x <= 0:
                continue
            tolerance_x = max(0.008 * image_width, 3.0 * module_x)
            if (
                abs(top["x0"] - bottom["x0"]) > tolerance_x
                or abs(top["x1"] - bottom["x1"]) > tolerance_x
                or abs(top["slope"] - bottom["slope"]) > 0.012
            ):
                continue
            center_x = (top["x0"] + top["x1"]) / 2.0
            separation = _bar_y(bottom, center_x) - _bar_y(top, center_x)
            expected = REPORT_BORDER_SEPARATION_MODULES * module_x
            if separation > 0 and abs(separation / expected - 1.0) < 0.25:
                pairs.append((top, bottom))
    return pairs


def _bilinear(
    image: np.ndarray,
    y: np.ndarray,
    x: np.ndarray,
) -> np.ndarray:
    """Sample an image at sub-pixel positions, clamped to the raster."""

    height, width = image.shape
    ys = np.clip(y, 0.0, height - 1.0)
    xs = np.clip(x, 0.0, width - 1.0)
    y0 = np.floor(ys).astype(np.intp)
    x0 = np.floor(xs).astype(np.intp)
    y1 = np.minimum(y0 + 1, height - 1)
    x1 = np.minimum(x0 + 1, width - 1)
    fy = ys - y0
    fx = xs - x0
    return (
        image[y0, x0] * (1.0 - fy) * (1.0 - fx)
        + image[y0, x1] * (1.0 - fy) * fx
        + image[y1, x0] * fy * (1.0 - fx)
        + image[y1, x1] * fy * fx
    )


def _decode_row(
    bits: np.ndarray,
    confidence: np.ndarray,
) -> tuple[np.ndarray, dict[str, int]]:
    """Decode one data row, spending its printed parity and row XOR.

    The strip already carries an even parity module per byte and a row XOR
    byte; the decoder used them only as counters.  Each is now also a single
    deterministic correction on the row's least reliable modules, so a strip
    still produces exactly one CRC candidate: fault tolerance rises without
    adding acceptance trials.  Every odd-parity byte is repaired, so
    ``parity_errors`` counts the repairs too.  An XOR syndrome whose weakest
    group is the XOR byte itself repairs nothing, because the data bytes are
    then the better evidence; ``xor_repairs`` therefore reports separately.
    """

    span = 9 * (REPORT_BYTES_PER_ROW + 1)
    groups = bits[4:4 + span].reshape(-1, 9).copy()
    margin = confidence[4:4 + span].reshape(-1, 9)
    odd = (groups[:, :8].sum(axis=1) % 2) != groups[:, 8]
    for index in np.flatnonzero(odd):
        groups[index, int(np.argmin(margin[index]))] ^= 1
    values = groups[:, :8].astype(np.int64) @ (1 << np.arange(7, -1, -1))
    data = values[:REPORT_BYTES_PER_ROW].copy()
    syndrome = int(np.bitwise_xor.reduce(data)) ^ int(values[-1])
    weakest = int(np.argmin(margin.min(axis=1)))
    xor_repairs = int(bool(syndrome) and weakest < REPORT_BYTES_PER_ROW)
    if xor_repairs:
        data[weakest] ^= syndrome
    return data.astype(np.uint8), {
        "sync_errors": int(
            tuple(int(bit) for bit in bits[:4]) != REPORT_ROW_SYNC
        ),
        "parity_errors": int(odd.sum()),
        "row_xor_errors": int(syndrome != 0),
        "xor_repairs": xor_repairs,
    }


def _decode_pair(
    image: np.ndarray,
    top: Mapping[str, float],
    bottom: Mapping[str, float],
) -> dict[str, Any] | None:
    """Clock-track and decode one fitted border pair."""

    height, width = image.shape
    x0 = (top["x0"] + bottom["x0"]) / 2.0
    x1 = (top["x1"] + bottom["x1"]) / 2.0
    module_x = (x1 - x0) / REPORT_WIDTH_MODULES
    center_x = (x0 + x1) / 2.0
    module_y = (
        _bar_y(bottom, center_x) - _bar_y(top, center_x)
    ) / REPORT_BORDER_SEPARATION_MODULES
    if module_x < 2.0 or module_y < 2.0:
        return None

    region_y0 = int(
        max(
            0,
            math.floor(
                min(_bar_y(top, x0), _bar_y(top, x1)) - 2 * module_y
            ),
        )
    )
    region_y1 = int(
        min(
            height,
            math.ceil(
                max(_bar_y(bottom, x0), _bar_y(bottom, x1))
                + 2 * module_y
            ),
        )
    )
    region = image[
        region_y0:region_y1,
        int(max(0, x0)):int(min(width, x1)),
    ]
    if region.size == 0:
        return None
    white = float(np.percentile(region, 95))
    black = float(np.percentile(region, 5))
    if white - black < 16.0 / 255.0:
        return None
    threshold = 0.5 * (white + black)

    xs = np.arange(
        int(math.ceil(x0 + 1.6 * module_x)),
        int(math.floor(x0 + (REPORT_WIDTH_MODULES - 1.6) * module_x)),
    )
    if len(xs) < 100:
        return None
    xs = np.clip(xs, 0, width - 1)
    module_y_x = (
        _bar_y(bottom, xs) - _bar_y(top, xs)
    ) / REPORT_BORDER_SEPARATION_MODULES
    half_height = max(1, int(round(0.30 * module_y)))
    offsets = np.arange(-half_height, half_height + 1)

    def band_dark(center_y: np.ndarray) -> np.ndarray:
        rows = np.clip(
            np.round(center_y).astype(int)[None, :] + offsets[:, None],
            0,
            height - 1,
        )
        return (image[rows, xs[None, :]] < threshold).mean(axis=0)

    top_clock_y = _bar_y(top, xs) + 2 * module_y_x
    bottom_clock_y = (
        _bar_y(top, xs)
        + (2 + REPORT_CLOCK_SEPARATION_MODULES) * module_y_x
    )
    clock_signal = band_dark(top_clock_y) - band_dark(bottom_clock_y)
    nominal_frequency = 1.0 / (2.0 * module_x)
    carrier = 2.0 * np.pi * nominal_frequency * (xs - xs[0])
    kernel = np.ones(max(3, int(round(4 * module_x))), dtype=np.float64)
    kernel /= kernel.size
    demodulated = np.convolve(
        clock_signal * np.exp(-1j * carrier), kernel, mode="same"
    )
    phase = np.maximum.accumulate(
        np.unwrap(np.angle(demodulated)) + carrier
    )

    middle_column = REPORT_INTERIOR_MODULES // 2
    anchor = int(
        np.clip(
            np.searchsorted(
                xs, x0 + (2 + middle_column + 0.5) * module_x
            ),
            1,
            len(xs) - 2,
        )
    )
    targets = (
        round(phase[anchor] / (2 * np.pi)) * 2 * np.pi
        - middle_column * np.pi
        + np.pi * np.arange(REPORT_INTERIOR_MODULES)
    )
    if targets[0] < phase[2] or targets[-1] > phase[-3]:
        return None
    column_x = np.interp(targets, phase, xs.astype(float))
    signal_at_columns = np.interp(column_x, xs, clock_signal)
    even = np.arange(REPORT_INTERIOR_MODULES) % 2 == 0
    clock_score = float(((signal_at_columns > 0) == even).mean())
    if clock_score < 0.95:
        return None

    module_y_columns = (
        _bar_y(bottom, column_x) - _bar_y(top, column_x)
    ) / REPORT_BORDER_SEPARATION_MODULES
    top_y_columns = _bar_y(top, column_x)
    column_x_int = np.clip(
        np.round(column_x).astype(int), 0, width - 1
    )
    centroid_half_height = max(2, int(round(0.9 * module_y)))
    centroid_offsets = np.arange(
        -centroid_half_height, centroid_half_height + 1
    )

    def centroid_track(
        row_index: int,
        columns: np.ndarray,
        base_delta: np.ndarray,
    ) -> np.ndarray:
        center_y = (
            top_y_columns[columns]
            + (2 + row_index) * module_y_columns[columns]
            + base_delta[columns]
        )
        rows = np.clip(
            np.round(center_y).astype(int)[None, :]
            + centroid_offsets[:, None],
            0,
            height - 1,
        )
        darkness = (
            image[rows, column_x_int[columns][None, :]] < threshold
        ).astype(np.float32)
        weight = darkness.sum(axis=0)
        good = (
            (weight > 0.5 * centroid_half_height)
            & (weight < 0.9 * len(centroid_offsets))
        )
        if good.sum() < 20:
            return base_delta
        centers = (
            darkness * centroid_offsets[:, None].astype(np.float32)
        ).sum(axis=0)[good] / weight[good]
        absolute_delta = (
            base_delta[columns] + np.round(center_y) - center_y
        )[good] + centers
        good_x = column_x[columns][good]
        half_window = 30.0 * module_x
        smoothed = np.asarray(
            [
                np.median(
                    absolute_delta[
                        max(0, np.searchsorted(good_x, value - half_window)):
                        np.searchsorted(good_x, value + half_window)
                    ]
                )
                for value in good_x
            ]
        )
        interpolated = np.interp(column_x, good_x, smoothed)
        return (
            np.clip(
                interpolated - base_delta,
                -0.4 * module_y,
                0.4 * module_y,
            )
            + base_delta
        )

    zero = np.zeros(REPORT_INTERIOR_MODULES)
    top_delta = centroid_track(0, np.flatnonzero(even), zero)
    bottom_delta = centroid_track(
        REPORT_CLOCK_SEPARATION_MODULES,
        np.flatnonzero(~even),
        zero,
    )
    row_deltas = [
        top_delta
        + (bottom_delta - top_delta)
        * row_index
        / REPORT_CLOCK_SEPARATION_MODULES
        for row_index in range(REPORT_DATA_ROWS + 2)
    ]

    taps = np.linspace(-2.0, 2.0, _APERTURE_TAPS)
    tap_weight = np.exp(-0.5 * taps ** 2)
    aperture_weight = (tap_weight[:, None] * tap_weight[None, :]).ravel()
    aperture_weight /= aperture_weight.sum()
    aperture_y, aperture_x = (
        grid.ravel()
        for grid in np.meshgrid(
            taps * (_APERTURE_SIGMA_MODULES * module_y),
            taps * (_APERTURE_SIGMA_MODULES * module_x),
            indexing="ij",
        )
    )

    def sample_rows(deltas: Sequence[np.ndarray]) -> list[np.ndarray]:
        result = []
        for row_index in range(REPORT_DATA_ROWS + 2):
            center_y = (
                top_y_columns
                + (2 + row_index) * module_y_columns
                + deltas[row_index]
            )
            result.append(
                (
                    _bilinear(
                        image,
                        center_y[:, None] + aperture_y[None, :],
                        column_x[:, None] + aperture_x[None, :],
                    )
                    * aperture_weight[None, :]
                ).sum(axis=1)
            )
        return result

    row_values = sample_rows(row_deltas)
    row_bits = [values < threshold for values in row_values]
    for _ in range(2):
        refined = list(row_deltas)
        for row_index in range(1, REPORT_DATA_ROWS + 1):
            isolated = (
                row_bits[row_index]
                & ~row_bits[row_index - 1]
                & ~row_bits[row_index + 1]
            )
            columns = np.flatnonzero(isolated)
            if len(columns) >= 30:
                refined[row_index] = centroid_track(
                    row_index, columns, row_deltas[row_index]
                )
        row_deltas = refined
        row_values = sample_rows(row_deltas)
        row_bits = [values < threshold for values in row_values]

    payload = bytearray(REPORT_PAYLOAD_BYTES)
    totals: Counter[str] = Counter()
    for row_index in range(REPORT_DATA_ROWS):
        data, counts = _decode_row(
            row_bits[1 + row_index].astype(np.uint8),
            np.abs(row_values[1 + row_index] - threshold),
        )
        payload[
            row_index * REPORT_BYTES_PER_ROW:
            (row_index + 1) * REPORT_BYTES_PER_ROW
        ] = data.tobytes()
        totals.update(counts)

    raw = bytes(payload)
    return {
        "payload": raw,
        "crc_ok": (
            crc16_ccitt(raw[:REPORT_CRC_OFFSET])
            == int.from_bytes(raw[REPORT_CRC_OFFSET:], "big")
        ),
        "magic_ok": (
            raw.startswith(REPORT_MAGIC)
            and raw[4] == REPORT_VERSION
        ),
        "clock_score": clock_score,
        "module_px": (float(module_x), float(module_y)),
        "skew_deg": math.degrees(math.atan(float(top["slope"]))),
        "sync_errors": totals["sync_errors"],
        "parity_errors": totals["parity_errors"],
        "row_xor_errors": totals["row_xor_errors"],
        "xor_repairs": totals["xor_repairs"],
    }


def _reflectance(image: np.ndarray) -> np.ndarray:
    values = np.asarray(image)
    if values.ndim != 2 or values.size == 0:
        raise ValueError("report-strip decoder requires a nonempty 2-D image")
    result = values.astype(np.float32, copy=False)
    if np.issubdtype(values.dtype, np.integer):
        result = result / np.float32(np.iinfo(values.dtype).max)
    elif float(np.nanmax(result)) > 1.0:
        result = result / np.float32(255.0)
    if not np.all(np.isfinite(result)):
        raise ValueError("report-strip image contains non-finite samples")
    return np.clip(result, 0.0, 1.0)


def _observation(
    raw: Mapping[str, Any],
    *,
    placement_index: int | None,
    rotated_180: bool,
) -> ReportStripObservation:
    payload = bytes(raw["payload"])
    report = None
    error = None
    if raw["crc_ok"] and raw["magic_ok"]:
        try:
            report = decode_report_payload(payload)
        except (TypeError, ValueError) as exc:
            error = str(exc)
    if report is not None:
        status = "ok"
    elif not raw["crc_ok"]:
        status = "crc_failed"
    elif not raw["magic_ok"]:
        status = "magic_mismatch"
    else:
        status = "payload_invalid"
    return ReportStripObservation(
        placement_index=placement_index,
        status=status,
        payload=payload,
        report=report,
        crc_ok=bool(raw["crc_ok"]),
        magic_ok=bool(raw["magic_ok"]),
        clock_score=float(raw["clock_score"]),
        module_px=tuple(float(value) for value in raw["module_px"]),
        skew_deg=float(raw["skew_deg"]),
        sync_errors=int(raw["sync_errors"]),
        parity_errors=int(raw["parity_errors"]),
        row_xor_errors=int(raw["row_xor_errors"]),
        xor_repairs=int(raw["xor_repairs"]),
        rotated_180=rotated_180,
        error=error,
    )


def decode_report_image(
    image: np.ndarray,
    *,
    placement_index: int | None = None,
) -> tuple[ReportStripObservation, ...]:
    """Find and decode current report strips in one canonical local image."""

    original = _reflectance(image)
    fallback: tuple[ReportStripObservation, ...] = ()
    for rotated in (False, True):
        view = original[::-1, ::-1] if rotated else original
        white = float(np.percentile(view, 90))
        black = float(np.percentile(view, 2))
        if white - black < 16.0 / 255.0:
            return ()
        threshold = 0.5 * (white + black)
        module_guess = max(
            2.0,
            min(
                view.shape[1] / REPORT_WIDTH_MODULES,
                view.shape[0] / REPORT_HEIGHT_MODULES,
            ),
        )
        pairs = _pair_bars(
            _find_bars(view < threshold, module_guess), view.shape[1]
        )
        observations = tuple(
            _observation(
                decoded,
                placement_index=placement_index,
                rotated_180=rotated,
            )
            for top, bottom in pairs
            if (decoded := _decode_pair(view, top, bottom)) is not None
        )
        if any(item.status == "ok" for item in observations):
            return observations
        if observations and not fallback:
            fallback = observations
    return fallback


def _region(
    value: ReportStripRegion | Mapping[str, Any],
    fallback_index: int,
) -> ReportStripRegion:
    if isinstance(value, ReportStripRegion):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("report-strip regions must be mappings or dataclasses")
    return ReportStripRegion(
        placement_index=int(
            value.get("placement_index", value.get("index", fallback_index))
        ),
        x_layout_dots=float(value["x_layout_dots"]),
        y_layout_dots=float(value["y_layout_dots"]),
        w_layout_dots=float(
            value.get("w_layout_dots", value.get("width_layout_dots"))
        ),
        h_layout_dots=float(
            value.get("h_layout_dots", value.get("height_layout_dots"))
        ),
    )


def _rectified_luma(
    source: RasterSource,
    affine: np.ndarray,
    region: ReportStripRegion,
    *,
    working_dpi: float,
) -> np.ndarray:
    if not math.isfinite(working_dpi) or working_dpi <= 0:
        raise ValueError("working_dpi must be positive")
    scale = working_dpi / LAYOUT_DPI
    margin = REPORT_SEARCH_MARGIN_LAYOUT_DOTS
    width = max(
        1,
        int(math.ceil((region.w_layout_dots + 2.0 * margin) * scale)),
    )
    height = max(
        1,
        int(math.ceil((region.h_layout_dots + 2.0 * margin) * scale)),
    )
    x = (
        region.x_layout_dots
        - margin
        + np.arange(width, dtype=np.float64) / scale
    )
    y = (
        region.y_layout_dots
        - margin
        + np.arange(height, dtype=np.float64) / scale
    )
    xx, yy = np.meshgrid(x, y)
    rgb = sample_layout_points(
        source,
        affine,
        xx,
        yy,
        max_crop_pixels=min(source.max_crop_pixels, 3_000_000),
        max_points_per_chunk=65_536,
    )
    return luma709(rgb)


def decode_report_strips(
    source: RasterSource,
    affine_layout_to_scan: np.ndarray,
    regions: Sequence[ReportStripRegion | Mapping[str, Any]],
    *,
    working_dpi: float = 600.0,
) -> tuple[ReportStripObservation, ...]:
    """Decode fixed report-strip regions after affine rectification.

    One best observation is returned per supplied region.  Missing and
    out-of-raster regions are preserved as structured observations so the
    analyzer can distinguish damage from unavailable capture geometry.
    """

    if isinstance(regions, (str, bytes, bytearray, Mapping)):
        raise TypeError("regions must be a sequence of report-strip records")
    output: list[ReportStripObservation] = []
    for fallback_index, value in enumerate(regions):
        region = _region(value, fallback_index)
        try:
            local = _rectified_luma(
                source,
                affine_layout_to_scan,
                region,
                working_dpi=working_dpi,
            )
        except OutOfRasterError as exc:
            output.append(
                ReportStripObservation(
                    placement_index=region.placement_index,
                    status="unobservable",
                    error=str(exc),
                )
            )
            continue
        candidates = decode_report_image(
            local, placement_index=region.placement_index
        )
        if not candidates:
            output.append(
                ReportStripObservation(
                    placement_index=region.placement_index,
                    status="not_found",
                    error="no current report-strip border/clock pair decoded",
                )
            )
            continue
        best = max(
            candidates,
            key=lambda item: (
                item.status == "ok",
                item.crc_ok,
                item.magic_ok,
                -int(item.parity_errors or 0),
                float(item.clock_score or 0.0),
            ),
        )
        output.append(best)
    return tuple(output)


def report_strip_consensus(
    observations: Sequence[ReportStripObservation],
) -> tuple[ReportPayload | None, dict[str, Any]]:
    """Require equality across all CRC-valid current strip payloads."""

    valid: list[ReportStripObservation] = []
    for item in observations:
        if (
            item.status != "ok"
            or not item.crc_ok
            or not item.magic_ok
            or item.payload is None
            or item.report is None
        ):
            continue
        try:
            decoded = decode_report_payload(item.payload)
        except (TypeError, ValueError):
            continue
        if decoded == item.report:
            valid.append(item)
    if not valid:
        return None, {
            "status": "no_valid_report_strip",
            "n_regions": len(observations),
            "n_valid": 0,
        }
    counts = Counter(item.payload for item in valid)
    if len(counts) != 1:
        return None, {
            "status": "report_strip_disagreement",
            "n_regions": len(observations),
            "n_valid": len(valid),
            "distinct_valid_payloads": len(counts),
            "placements": [item.placement_index for item in valid],
        }
    return valid[0].report, {
        "status": "ok",
        "n_regions": len(observations),
        "n_valid": len(valid),
        "distinct_valid_payloads": 1,
        "placements": [item.placement_index for item in valid],
    }


def normalize_report_strips(
    observations: Sequence[ReportStripObservation],
) -> dict[str, Any]:
    """Normalize strip evidence for the characterization analyzer report."""

    report, consensus = report_strip_consensus(observations)
    return {
        "identity": None if report is None else report.identity.to_dict(),
        "device_readback": (
            None if report is None else report.device_readback.to_dict()
        ),
        "strip_diagnostics": [
            observation.diagnostics_dict() for observation in observations
        ],
        "consensus": consensus,
    }



__all__ = [
    "ReportStripObservation",
    "ReportStripRegion",
    "decode_report_image",
    "decode_report_strips",
    "normalize_report_strips",
    "report_strip_consensus",
]
