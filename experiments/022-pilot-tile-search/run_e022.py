#!/usr/bin/env python
"""Run E021 -> E022 pilot-field placement and render three-pane diagnostics.

  env/bin/python experiments/022-pilot-tile-search/run_e022.py SCAN \
      --dpi 1600 --format e018-v3-c3 --diag build/diag

The final PNG contains: A) E021 scan regions and placement states, B) placed
scrap footprints in page coordinates, C) addressed pilot-tile evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import formats, pilotdiag, pilotsearch, platen  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

# the e018 descriptor lives in the format registry (single seed source —
# the 012.3 rule); this alias keeps existing callers/tests working.
E018 = next(f for f in formats.FORMAT_REGISTRY
            if f.format_id == "e018-v3-c3")

# Backward-compatible names for existing qualification scripts.  The public
# implementations live in paperholo.pilotdiag so integrated receivers do not
# import this CLI module (or its formerly-private helpers).
COLORS = pilotdiag.COLORS
STATE_COLORS = pilotdiag.STATE_COLORS
_font = pilotdiag.font
_json_default = pilotdiag.json_default
_normal_preview = pilotdiag.normal_preview
_panel_title = pilotdiag.panel_title
scan_panel = pilotdiag.scan_panel
_page_base = pilotdiag.page_base
placement_panel = pilotdiag.placement_panel
pilot_panel = pilotdiag.pilot_panel
compose_diagnostic = pilotdiag.compose_diagnostic
render_diagnostic = pilotdiag.render_diagnostic
diagnostic_png_bytes = pilotdiag.diagnostic_png_bytes
search_result_report = pilotdiag.search_result_report


def load_image(path: Path) -> np.ndarray:
    if path.suffix.lower() in (".tif", ".tiff"):
        arr = tifffile.TiffFile(str(path)).pages[0].asarray(out="memmap")
        if arr.ndim == 3:
            return arr[..., :3].mean(axis=2, dtype=np.float32)
        return arr
    return np.asarray(Image.open(path).convert("L"))


def resolve_format(format_id: str) -> formats.FormatDescriptor:
    for descriptor in formats.FORMAT_REGISTRY:
        if descriptor.format_id == format_id:
            return descriptor
    names = ", ".join(row.format_id for row in formats.FORMAT_REGISTRY)
    raise ValueError(f"unknown format {format_id!r}; choose one of: {names}")


def result_report(
    result: pilotsearch.SearchResult,
    descriptor: formats.FormatDescriptor,
    survey: platen.PayloadSurvey,
) -> dict:
    report = pilotdiag.search_result_report(result, descriptor)
    report["survey"] = {
        "regions": len(survey.regions),
        "c_dots": survey.c_dots,
        "cell_pitch_px": survey.cell_pitch_px,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--dpi", type=float, required=True)
    parser.add_argument("--format", default="e018-v3-c3")
    parser.add_argument("--pages", default="0",
                        help="comma-separated legal page numbers")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--diag", type=Path, default=None,
                        help="write an evolving three-pane PNG after each scrap")
    parser.add_argument("--no-bch-first", action="store_true")
    args = parser.parse_args()

    descriptor = resolve_format(args.format)
    pages = tuple(int(value) for value in args.pages.split(","))
    image = load_image(args.image)
    print(f"E021 survey: {args.image} ({image.shape}, dpi={args.dpi:g})",
          flush=True)
    survey = platen.detect_payload_regions(image, dpi=args.dpi)
    print(f"  regions={len(survey.regions)} c={survey.c_dots} "
          f"pitch={survey.cell_pitch_px}", flush=True)

    out = args.out or HERE / "build" / f"{args.image.stem}_e022.png"
    report_path = args.report or out.with_suffix(".json")
    empty = pilotsearch.SearchResult()
    frame_no = 0
    diag_enabled = args.diag is not None
    if args.diag is not None:
        args.diag.mkdir(parents=True, exist_ok=True)
        pilotdiag.render_diagnostic(
            image, survey, empty, descriptor,
            args.diag / f"frame_{frame_no:04d}.png",
        )

    def on_region(result: pilotsearch.SearchResult, region_index: int) -> None:
        nonlocal frame_no, diag_enabled
        state = result.region_states[region_index]
        n_place = sum(row.region_index == region_index
                      for row in result.placements)
        print(f"  region {region_index}: {state}, placements={n_place}",
              flush=True)
        if diag_enabled and args.diag is not None:
            frame_no += 1
            try:
                pilotdiag.render_diagnostic(
                    image, survey, result, descriptor,
                    args.diag / f"frame_{frame_no:04d}.png",
                    active_region=region_index,
                )
            except Exception as exc:  # observer failure must not stop E022
                diag_enabled = False
                print(f"  diag disabled after render error: {exc!r}",
                      flush=True)

    config = pilotsearch.SearchConfig(bch_first=not args.no_bch_first)
    result = pilotsearch.search_survey(
        image, survey, descriptor, pages=pages, config=config,
        scan_dpi=args.dpi, on_region=on_region,
    )
    pilotdiag.render_diagnostic(image, survey, result, descriptor, out)
    report = result_report(result, descriptor, survey)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(
        report, indent=2, sort_keys=True, default=pilotdiag.json_default
    ) + "\n")
    print(f"E022: placements={len(result.placements)} "
          f"pilot_tiles={len(result.tiles)} total={result.timings['total_s']:.2f}s")
    print(f"  wrote {out}")
    print(f"  wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
