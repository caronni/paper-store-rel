"""Reusable E021/E022 diagnostic and reporting primitives.

These functions render the qualified E022 A/B/C view but own no receiver
state.  Experiment runners may compose more panes around them without
importing another CLI script or reaching through private helper names.
"""
from __future__ import annotations

import io
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from paperholo import formats, pilotsearch, platen


COLORS = [
    (31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
    (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127),
    (188, 189, 34), (23, 190, 207),
]
STATE_COLORS = {
    "pending": (245, 174, 65),
    "accepted": (30, 150, 80),
    "redundant": (100, 150, 165),
    "unresolved": (205, 55, 55),
    "pose_refused": (125, 125, 125),
}


def font(size: int):
    for name in ("DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def json_default(value):
    """JSON adapter shared by E022 reports."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def normal_preview(
    image: np.ndarray, target_width: int
) -> tuple[Image.Image, float]:
    stride = max(1, int(np.ceil(image.shape[1] / target_width)))
    preview = np.asarray(image[::stride, ::stride], np.float32)
    lo, hi = np.percentile(preview, (1.0, 99.0))
    grey = np.clip(
        (preview - lo) / max(hi - lo, 1e-6) * 255, 0, 255
    )
    out = Image.fromarray(grey.astype(np.uint8)).convert("RGB")
    scale = target_width / out.width
    out = out.resize((target_width, max(1, int(round(out.height * scale)))))
    return out, scale / stride


def panel_title(image: Image.Image, title: str) -> Image.Image:
    bar = 34
    out = Image.new("RGB", (image.width, image.height + bar), "white")
    out.paste(image, (0, bar))
    draw = ImageDraw.Draw(out)
    draw.text((9, 8), title, fill=(25, 25, 25), font=font(15))
    draw.line((0, bar - 1, image.width, bar - 1), fill=(190, 190, 190))
    return out


def _progress_value(progress, name: str, default=None):
    if progress is None:
        return default
    if isinstance(progress, Mapping):
        return progress.get(name, default)
    return getattr(progress, name, default)


def _window_progress_title(progress) -> str:
    if progress is None:
        return ""
    ordinal = _progress_value(progress, "ordinal", "?")
    total = _progress_value(progress, "queue_total", "?")
    depth = _progress_value(progress, "depth", "?")
    stage = _progress_value(progress, "stage", "window")
    stage = {
        "window_open": "pose/FFT",
        "pose_fitted": "pose/sample",
        "window_complete": "complete",
    }.get(stage, stage)
    bits = [f"w{ordinal}/{total}", f"d{depth}", str(stage)]
    return " · " + " ".join(bits)


def scan_panel(
    image: np.ndarray,
    survey: platen.PayloadSurvey,
    result: pilotsearch.SearchResult,
    *,
    width: int,
    active_region: int | None,
    window_progress=None,
) -> Image.Image:
    """Pane A: current scan regions and their E022 outcomes."""
    panel, scale = normal_preview(image, width)
    draw = ImageDraw.Draw(panel)
    for region_index, region in enumerate(survey.regions):
        state = result.region_states.get(region_index, "pending")
        color = STATE_COLORS.get(state, (125, 125, 125))
        if region_index == active_region:
            color = (255, 215, 0)
        y0, x0, h, w = region.bbox
        box = (
            x0 * scale,
            y0 * scale,
            (x0 + w) * scale,
            (y0 + h) * scale,
        )
        draw.rectangle(box, outline=color, width=3)
        routes = [
            p.method for p in result.placements
            if p.region_index == region_index
        ]
        suffix = f" {routes[0]}" if routes else ""
        label = f"{region_index} {state}{suffix}"
        draw.text(
            (box[0] + 3, max(0, box[1] - 15)),
            label,
            fill=color,
            font=font(13),
            stroke_width=2,
            stroke_fill=(0, 0, 0),
        )

    # The in-flight window is observer-only: cyan bounds locate exactly what
    # E022 is fitting, while the two lattice basis vectors expose the fitted
    # local angle, pitch, and shear directly on the source raster.
    bbox = _progress_value(window_progress, "scan_bbox_yxhw_px")
    if bbox is not None:
        y0, x0, height, box_width = (float(value) for value in bbox)
        box = (x0 * scale, y0 * scale,
               (x0 + box_width) * scale, (y0 + height) * scale)
        draw.rectangle(box, outline=(20, 225, 235), width=4)
        label = _window_progress_title(window_progress).lstrip(" ·")
        draw.text(
            (box[0] + 4, min(panel.height - 16, max(1, box[1] + 3))),
            label, fill=(20, 225, 235), font=font(12),
            stroke_width=2, stroke_fill=(0, 0, 0))
    origin = _progress_value(window_progress, "pose_origin_yx")
    jacobian = _progress_value(window_progress, "jacobian_yx")
    if origin is not None and jacobian is not None:
        oy, ox = (float(value) for value in origin)
        jac = np.asarray(jacobian, np.float64)
        if jac.shape == (2, 2) and np.isfinite(jac).all():
            axis_cells = 20.0
            start = (ox * scale, oy * scale)
            # J columns are the +v (row) and +u (column) lattice vectors.
            colors = ((255, 90, 185), (80, 245, 125))
            labels = ("+v", "+u")
            for column, (color, label) in enumerate(zip(colors, labels)):
                end_y = oy + axis_cells * jac[0, column]
                end_x = ox + axis_cells * jac[1, column]
                end = (end_x * scale, end_y * scale)
                draw.line((start, end), fill=color, width=4)
                draw.text(end, label, fill=color, font=font(11),
                          stroke_width=2, stroke_fill=(0, 0, 0))
            radius = 4
            draw.ellipse((start[0] - radius, start[1] - radius,
                          start[0] + radius, start[1] + radius),
                         fill=(255, 255, 255), outline=(20, 20, 20), width=1)
    return panel_title(
        panel, "A  E021 scan regions / E022 outcomes"
        + _window_progress_title(window_progress))


def page_base(spec, width: int) -> tuple[Image.Image, float]:
    h, w = spec.page_cells_yx
    height = max(1, int(round(width * h / w)))
    return Image.new("RGB", (width, height), (246, 246, 242)), width / w


def placement_panel(
    result: pilotsearch.SearchResult, spec, *, width: int,
    page: int | None = None,
    window_progress=None,
) -> Image.Image:
    """Pane B: placed scrap support in canonical page coordinates."""
    panel, scale = page_base(spec, width)
    page_h, page_w = spec.page_cells_yx
    layer = np.full((page_h, page_w, 3), 246, np.uint8)
    for placement in result.placements:
        if page is not None and placement.page != page:
            continue
        color = np.asarray(
            COLORS[placement.region_index % len(COLORS)], np.uint8
        )
        points = placement.page_cells_yx
        if points.size:
            old = layer[points[:, 0], points[:, 1]].astype(np.uint16)
            layer[points[:, 0], points[:, 1]] = (
                (old * 2 + color.astype(np.uint16)) // 3
            ).astype(np.uint8)
    raster = Image.fromarray(layer).resize(
        panel.size, Image.Resampling.NEAREST
    )
    panel.paste(raster)
    draw = ImageDraw.Draw(panel)
    for placement in result.placements:
        if page is not None and placement.page != page:
            continue
        y0, x0 = placement.origin_yx
        shape = (placement.window.h, placement.window.w)
        rh, rw = np.rot90(np.empty(shape), placement.rot_k).shape
        color = COLORS[placement.region_index % len(COLORS)]
        redundant = getattr(placement, "redundant", False)
        draw.rectangle(
            (
                x0 * scale,
                y0 * scale,
                (x0 + rw) * scale,
                (y0 + rh) * scale,
            ),
            outline=color,
            width=1 if redundant else 2,
        )
        prefix = f"{placement.scan_id}/" if placement.scan_id else ""
        region_label = placement.diagnostics.get(
            "source_region_index", placement.region_index
        )
        suffix = " dup" if redundant else ""
        draw.text(
            (x0 * scale + 2, y0 * scale + 2),
            f"{prefix}r{region_label}:{placement.method}{suffix}",
            fill=color,
            font=font(12),
            stroke_width=2,
            stroke_fill=(255, 255, 255),
        )
    candidate_page = _progress_value(window_progress, "placement_page")
    candidate_origin = _progress_value(
        window_progress, "placement_origin_yx")
    candidate_shape = _progress_value(
        window_progress, "window_shape_yx_cells")
    candidate_rot = _progress_value(window_progress, "placement_rot_k")
    if (candidate_origin is not None and candidate_shape is not None
            and candidate_rot is not None
            and (page is None or int(candidate_page) == int(page))):
        y0, x0 = (int(value) for value in candidate_origin)
        height, box_width = (int(value) for value in candidate_shape)
        if int(candidate_rot) % 2:
            height, box_width = box_width, height
        box = (x0 * scale, y0 * scale,
               (x0 + box_width) * scale, (y0 + height) * scale)
        draw.rectangle(box, outline=(190, 45, 230), width=4)
        method = _progress_value(window_progress, "method") or "candidate"
        draw.text(
            (box[0] + 2, box[1] + 2), str(method),
            fill=(190, 45, 230), font=font(12),
            stroke_width=2, stroke_fill=(255, 255, 255))
    return panel_title(
        panel,
        "B  placed scrap support on canonical page (thin=redundant)",
    )


def pilot_panel(
    result: pilotsearch.SearchResult, spec, *, width: int, page: int = 0,
) -> Image.Image:
    """Pane C: addressed pilot-tile coverage and BCH state."""
    panel, scale = page_base(spec, width)
    draw = ImageDraw.Draw(panel)
    period = spec.pilot.period_cells
    tile_h, tile_w = spec.page_tiles_yx
    for tile_y in range(tile_h):
        for tile_x in range(tile_w):
            key = (page, tile_y, tile_x)
            tile = result.tiles.get(key)
            x0, y0 = tile_x * period * scale, tile_y * period * scale
            x1 = (tile_x + 1) * period * scale
            y1 = (tile_y + 1) * period * scale
            if tile is None:
                fill = (238, 238, 238)
                outline = (215, 215, 215)
            elif tile.bch_ok:
                fill = (118, 196, 130)
                outline = (25, 120, 55)
            elif tile.observed_sites >= 20:
                fill = (120, 175, 225)
                outline = (30, 105, 175)
            else:
                fill = (250, 198, 110)
                outline = (210, 130, 35)
            draw.rectangle((x0, y0, x1, y1), fill=fill, outline=outline)
            if tile is not None and scale * period >= 12:
                draw.text(
                    (x0 + 2, y0 + 1),
                    str(tile.observed_sites),
                    fill=(20, 20, 20),
                    font=font(9),
                )
    title = (
        "C  registered pilot tiles: green=BCH read, blue=placed, "
        "orange=partial"
    )
    return panel_title(panel, title)


def compose_diagnostic(
    image: np.ndarray,
    survey: platen.PayloadSurvey,
    result: pilotsearch.SearchResult,
    descriptor: formats.FormatDescriptor,
    *,
    reference_result: pilotsearch.SearchResult | None = None,
    active_region: int | None = None,
    window_progress=None,
    page: int | None = None,
    panel_width: int = 720,
) -> Image.Image:
    """Compose E022's panes A, B, and C into one canvas."""
    reference = result if reference_result is None else reference_result
    panels = [
        scan_panel(
            image,
            survey,
            result,
            width=panel_width,
            active_region=active_region,
            window_progress=window_progress,
        ),
        placement_panel(reference, descriptor.spec(), width=panel_width,
                        page=page, window_progress=window_progress),
        pilot_panel(reference, descriptor.spec(), width=panel_width,
                    page=0 if page is None else page),
    ]
    height = max(panel.height for panel in panels)
    canvas = Image.new(
        "RGB", (sum(panel.width for panel in panels), height), (255, 255, 255)
    )
    x = 0
    for panel in panels:
        canvas.paste(panel, (x, 0))
        x += panel.width
    return canvas


def render_diagnostic(
    image: np.ndarray,
    survey: platen.PayloadSurvey,
    result: pilotsearch.SearchResult,
    descriptor: formats.FormatDescriptor,
    out: Path,
    *,
    reference_result: pilotsearch.SearchResult | None = None,
    active_region: int | None = None,
    window_progress=None,
    page: int | None = None,
    panel_width: int = 720,
) -> Path:
    canvas = compose_diagnostic(
        image,
        survey,
        result,
        descriptor,
        reference_result=reference_result,
        active_region=active_region, window_progress=window_progress,
        page=page,
        panel_width=panel_width,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def diagnostic_png_bytes(
    image: np.ndarray,
    survey: platen.PayloadSurvey,
    result: pilotsearch.SearchResult,
    descriptor: formats.FormatDescriptor,
    *,
    reference_result: pilotsearch.SearchResult | None = None,
    active_region: int | None = None,
    window_progress=None,
    page: int | None = None,
    panel_width: int = 720,
) -> bytes:
    canvas = compose_diagnostic(
        image,
        survey,
        result,
        descriptor,
        reference_result=reference_result,
        active_region=active_region, window_progress=window_progress,
        page=page,
        panel_width=panel_width,
    )
    stream = io.BytesIO()
    canvas.save(stream, format="PNG")
    return stream.getvalue()


def search_result_report(
    result: pilotsearch.SearchResult,
    descriptor: formats.FormatDescriptor,
) -> dict:
    """Stable JSON-ready account of an E022 search result."""
    placements = []
    for row in result.placements:
        placements.append({
            "region": row.region_index,
            "window_yxhw": [
                row.window.y, row.window.x, row.window.h, row.window.w
            ],
            "page": row.page,
            "origin_yx": list(row.origin_yx),
            "rot_k": row.rot_k,
            "method": row.method,
            "scan_id": row.scan_id,
            "component": row.component,
            "mismatch": row.mismatch,
            "validation_mismatch": row.validation_mismatch,
            "rival_mismatch": row.rival_mismatch,
            "rival_searched": row.rival_searched,
            "predicted_residual_cells": row.predicted_residual_cells,
            "support": row.support,
            "elapsed_s": row.elapsed_s,
            "bch_errors": row.bch_errors,
            "redundant": getattr(row, "redundant", False),
            "pose": {
                "origin_yx": list(row.pose.origin_yx),
                "jacobian_yx": [list(v) for v in row.pose.jacobian_yx],
                "angle_deg": row.pose.angle_deg,
                "pitch_px": row.pose.pitch_px,
                "footing_factor": row.pose.footing_factor,
            },
            "diagnostics": row.diagnostics,
        })
    tiles = []
    for key, tile in sorted(result.tiles.items()):
        tiles.append({
            "page_tile_yx": list(key),
            "observed_sites": tile.observed_sites,
            "bch_ok": tile.bch_ok,
            "bch_attempted": tile.bch_attempted,
            "bch_refused": tile.bch_refused,
            "bch_errors": tile.bch_errors,
            "bch_erasures": tile.bch_erasures,
            "bch_elapsed_s": tile.bch_elapsed_s,
        })
    return {
        "format_id": descriptor.format_id,
        "region_states": result.region_states,
        "placements": placements,
        "pilot_tiles": tiles,
        "timings": result.timings,
        "diagnostics": result.diagnostics,
    }
