"""Read-only four-pane diagnostics for the integrated E023b receiver."""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from . import ldpc, payloaddec, pilotdiag, pilotsearch, platen, receiver
from .formats import FormatDescriptor


TILE_COLORS = {
    "certified": (98, 190, 110),
    "attempted_failed": (214, 69, 60),
    "below_attempt_floor": (245, 190, 96),
    "unobserved": (233, 233, 233),
    "degenerate": (170, 170, 185),
}


@dataclass
class DiagProgress:
    """Transient observer state; never persisted into ReceiverSession."""

    phase: str = "idle"
    tile_coverage: dict[tuple[int, int, int], float] = field(
        default_factory=dict)
    active_tiles: set[tuple[int, int, int]] = field(default_factory=set)
    attempt_ready: set[tuple[int, int, int]] = field(default_factory=set)
    refused_windows: int = 0


def work_plan_progress(record: receiver.ScanRecord,
                       *, phase: str = "payload_plan") -> DiagProgress:
    return DiagProgress(
        phase=phase,
        tile_coverage={key: row.geometric_coverage
                       for key, row in record.work_plan.items()},
    )


def _inset_box(
    box: tuple[float, float, float, float], inset: float,
) -> tuple[float, float, float, float]:
    """Inset a display box without reversing a subpixel edge rectangle."""
    x0, y0, x1, y1 = box
    x_pad = min(float(inset), max(0.0, (x1 - x0) / 2.0))
    y_pad = min(float(inset), max(0.0, (y1 - y0) / 2.0))
    return x0 + x_pad, y0 + y_pad, x1 - x_pad, y1 - y_pad


def ldpc_panel(
    session: receiver.ReceiverSession,
    *,
    width: int,
    page: int,
    progress: DiagProgress | None = None,
) -> Image.Image:
    """Pane D: committed states plus an observer-only current-scan overlay."""
    spec = session.decode.spec
    panel, scale = pilotdiag.page_base(spec, width)
    draw = ImageDraw.Draw(panel)
    tc = ldpc.TILE_CELLS
    states = payloaddec.full_tile_states(session.decode)
    for (pg, ty, tx), state in states.items():
        if pg != page:
            continue
        x0, y0 = tx * tc * scale, ty * tc * scale
        x1 = min(spec.page_cells_yx[1], (tx + 1) * tc) * scale
        y1 = min(spec.page_cells_yx[0], (ty + 1) * tc) * scale
        draw.rectangle((x0, y0, x1, y1), fill=TILE_COLORS[state],
                       outline=(252, 252, 252))

    if progress is not None:
        for key, coverage in progress.tile_coverage.items():
            pg, ty, tx = key
            if pg != page:
                continue
            x0, y0 = tx * tc * scale, ty * tc * scale
            x1 = min(spec.page_cells_yx[1], (tx + 1) * tc) * scale
            y1 = min(spec.page_cells_yx[0], (ty + 1) * tc) * scale
            blue = int(100 + 120 * max(0.0, min(float(coverage), 1.0)))
            draw.rectangle(_inset_box((x0, y0, x1, y1), 1),
                           outline=(45, 115, blue), width=2)
        for pg, ty, tx in progress.attempt_ready:
            if pg != page:
                continue
            x0, y0 = tx * tc * scale, ty * tc * scale
            x1 = min(spec.page_cells_yx[1], (tx + 1) * tc) * scale
            y1 = min(spec.page_cells_yx[0], (ty + 1) * tc) * scale
            draw.rectangle(_inset_box((x0, y0, x1, y1), 2),
                           outline=(240, 170, 30), width=3)
        for pg, ty, tx in progress.active_tiles:
            if pg != page:
                continue
            x0, y0 = tx * tc * scale, ty * tc * scale
            x1 = min(spec.page_cells_yx[1], (tx + 1) * tc) * scale
            y1 = min(spec.page_cells_yx[0], (ty + 1) * tc) * scale
            draw.rectangle(_inset_box((x0, y0, x1, y1), 4),
                           outline=(135, 70, 175), width=2)

    counts: dict[str, int] = {}
    for (pg, _ty, _tx), state in states.items():
        if pg == page:
            counts[state] = counts.get(state, 0) + 1
    phase = "" if progress is None else f" · {progress.phase}"
    refused = ("" if progress is None or not progress.refused_windows else
               f" · refused={progress.refused_windows}")
    title = "D  LDPC p{}: {}{}".format(
        page,
        " ".join(f"{state}={counts.get(state, 0)}" for state in (
            "certified", "attempted_failed", "below_attempt_floor",
            "unobserved", "degenerate")),
        phase + refused,
    )
    return pilotdiag.panel_title(panel, title)


def compose_diagnostic(
    image,
    survey: platen.PayloadSurvey,
    current: pilotsearch.SearchResult,
    combined: pilotsearch.SearchResult,
    descriptor: FormatDescriptor,
    session: receiver.ReceiverSession,
    *,
    page: int,
    active_region: int | None = None,
    pilot_progress=None,
    progress: DiagProgress | None = None,
    panel_width: int = 600,
) -> Image.Image:
    """Compose causal A/B/C/D panes for one logical page."""
    panels = [
        pilotdiag.scan_panel(image, survey, current, width=panel_width,
                             active_region=active_region,
                             window_progress=pilot_progress),
        pilotdiag.placement_panel(combined, descriptor.spec(),
                                  width=panel_width, page=page,
                                  window_progress=pilot_progress),
        pilotdiag.pilot_panel(combined, descriptor.spec(), width=panel_width,
                              page=page),
        ldpc_panel(session, width=panel_width, page=page, progress=progress),
    ]
    height = max(panel.height for panel in panels)
    canvas = Image.new("RGB", (sum(panel.width for panel in panels), height),
                       (255, 255, 255))
    x = 0
    for panel in panels:
        canvas.paste(panel, (x, 0))
        x += panel.width
    return canvas


def diagnostic_png_bytes(*args, **kwargs) -> bytes:
    image = compose_diagnostic(*args, **kwargs)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()
