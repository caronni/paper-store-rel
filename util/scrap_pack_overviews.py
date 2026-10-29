#!/usr/bin/env python3
"""Render exhaustive, bounded source/packed-target scrap-pack overviews.

The output tree mirrors input paths and contains one ``*.overview.png`` per
TIFF/PNG.  Native packed canvases are never composed: source crops are sampled
directly into a bounded target preview, so multi-gigabyte scans remain safe.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import re
import textwrap
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import numpy as np
import tifffile
from PIL import Image, ImageDraw, ImageFont, ImageOps, PngImagePlugin

try:
    from util import scrap_pack
except ModuleNotFoundError:  # Running as ``python util/scrap_pack_overviews.py``.
    import scrap_pack  # type: ignore[no-redef]


Image.MAX_IMAGE_PIXELS = None
IMAGE_SUFFIXES = {".png", ".tif", ".tiff"}
ADMIN_DIRS = {
    "env", ".venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
PANEL_WIDTH = 800
PANEL_HEIGHT = 600
MARGIN = 24
HEADER_HEIGHT = 112
LABEL_HEIGHT = 34


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


FONT = _font(18)
SMALL_FONT = _font(15)
BOLD_FONT = _font(20)


def discover_images(
    root: Path,
    output_root: Path,
    *,
    include_admin: bool = False,
) -> list[Path]:
    """Freeze repository images, excluding administrative/generated trees."""

    root = root.resolve()
    output_root = output_root.resolve()
    paths: list[Path] = []
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        dirs[:] = sorted(
            name for name in dirs
            if name != ".git"
            and (include_admin or name not in ADMIN_DIRS)
            and (current_path / name).resolve() != output_root
            and (include_admin or not (
                name == "worktrees"
                and current_path.name == ".claude"
            ))
        )
        for name in sorted(files):
            path = current_path / name
            if path.suffix.lower() in IMAGE_SUFFIXES:
                paths.append(path.resolve())
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def overview_path(root: Path, output_root: Path, source: Path) -> Path:
    relative = source.relative_to(root)
    return output_root / relative.parent / f"{relative.name}.overview.png"


def _numeric_resolution(value: Any) -> float | None:
    try:
        if isinstance(value, tuple) and len(value) == 2:
            return float(value[0]) / float(value[1])
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def metadata_dpi(path: Path) -> float | None:
    try:
        if path.suffix.lower() in {".tif", ".tiff"}:
            with tifffile.TiffFile(path) as tif:
                page = tif.pages[0]
                x_tag = page.tags.get("XResolution")
                y_tag = page.tags.get("YResolution")
                if x_tag is None or y_tag is None:
                    return None
                x = _numeric_resolution(x_tag.value)
                y = _numeric_resolution(y_tag.value)
                if x is None or y is None or not math.isclose(x, y, rel_tol=0.02):
                    return None
                unit_tag = page.tags.get("ResolutionUnit")
                unit = int(unit_tag.value) if unit_tag is not None else 2
                if unit == 3:  # centimetre
                    x *= 2.54
                elif unit != 2:  # none/unknown
                    return None
                return x if 50 <= x <= 10000 else None
        with Image.open(path) as image:
            dpi = image.info.get("dpi")
            if not dpi:
                return None
            x, y = float(dpi[0]), float(dpi[1])
            if not math.isclose(x, y, rel_tol=0.02):
                return None
            return x if 50 <= x <= 10000 else None
    except Exception:
        return None


def infer_cell_px(path: Path, relative: Path) -> tuple[float, str, float | None]:
    """Use explicit ppc, then unambiguous cN+DPI, else tool default 24."""

    text = relative.as_posix().lower()
    explicit = re.findall(r"(?<![0-9.])(\d+(?:\.\d+)?)\s*ppc(?![a-z])", text)
    if len(set(explicit)) == 1:
        value = float(explicit[0])
        if value > 0:
            return value, "path ppc", None

    architectures = set(re.findall(
        r"(?:^|[^a-z0-9])c([23])(?=$|[^a-z0-9])", text
    ))
    architectures.update(re.findall(
        r"(?<=\d)c([23])(?=(?:hp|canon))", text
    ))
    path_dpi = re.findall(
        r"(?<!\d)(300|600|1200|1600|2400|4800)(?:\s*dpi)?(?!\d)",
        text,
    )
    dpi: float | None = None
    dpi_reason = ""
    if len(set(path_dpi)) == 1:
        dpi = float(path_dpi[0])
        dpi_reason = "path"
    else:
        dpi = metadata_dpi(path)
        if dpi is not None:
            dpi_reason = "metadata"
    if len(architectures) == 1 and dpi is not None:
        architecture = int(next(iter(architectures)))
        cell = dpi * architecture / 600.0
        if cell > 0:
            return cell, f"c{architecture} + {dpi_reason} DPI", dpi
    return 24.0, "fallback default", dpi


def tiff_photometric(path: Path) -> str | None:
    if path.suffix.lower() not in {".tif", ".tiff"}:
        return None
    try:
        with tifffile.TiffFile(path) as tif:
            value = tif.pages[0].photometric
            return getattr(value, "name", str(value)).upper()
    except Exception:
        return None


def _u8(array: np.ndarray) -> np.ndarray:
    if array.dtype == np.uint8:
        return np.asarray(array)
    if array.dtype.kind == "u":
        maximum = float(np.iinfo(array.dtype).max)
        return np.clip(array.astype(np.float32) * (255.0 / maximum), 0, 255).astype(np.uint8)
    work = np.asarray(array, np.float32)
    finite = work[np.isfinite(work)]
    if not finite.size:
        return np.zeros(work.shape, np.uint8)
    lo, hi = float(np.min(finite)), float(np.max(finite))
    if hi <= lo:
        return np.zeros(work.shape, np.uint8)
    return np.clip((work - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def _array_image(array: np.ndarray) -> Image.Image:
    pixels = _u8(np.asarray(array))
    if pixels.ndim == 2:
        return Image.fromarray(pixels, "L").convert("RGB")
    if pixels.shape[-1] == 4:
        foreground = Image.fromarray(pixels, "RGBA")
        checker = Image.new("RGB", foreground.size, (235, 235, 235))
        tile = Image.new("RGB", foreground.size, (255, 255, 255))
        draw = ImageDraw.Draw(tile)
        for y in range(0, foreground.height, 24):
            for x in range(0, foreground.width, 24):
                if (x // 24 + y // 24) % 2:
                    draw.rectangle((x, y, x + 23, y + 23), fill=(235, 235, 235))
        checker.paste(tile)
        checker.paste(foreground, mask=foreground.getchannel("A"))
        return checker
    return Image.fromarray(pixels[..., :3], "RGB")


def _fit_size(width: int, height: int) -> tuple[int, int]:
    scale = min(PANEL_WIDTH / max(width, 1), PANEL_HEIGHT / max(height, 1))
    return max(1, round(width * scale)), max(1, round(height * scale))


def _sample_region(
    array: np.ndarray,
    y0: int,
    x0: int,
    y1: int,
    x1: int,
    out_height: int,
    out_width: int,
) -> np.ndarray:
    height, width = y1 - y0, x1 - x0
    ys = y0 + np.minimum(
        height - 1,
        ((np.arange(out_height, dtype=np.float64) + 0.5) * height / out_height).astype(np.int64),
    )
    xs = x0 + np.minimum(
        width - 1,
        ((np.arange(out_width, dtype=np.float64) + 0.5) * width / out_width).astype(np.int64),
    )
    return np.asarray(array[ys[:, None], xs[None, :]])


def render_source(array: np.ndarray, boxes: list[scrap_pack.Box]) -> Image.Image:
    height, width = array.shape[:2]
    out_width, out_height = _fit_size(width, height)
    sampled = _sample_region(array, 0, 0, height, width, out_height, out_width)
    image = _array_image(sampled)
    draw = ImageDraw.Draw(image, "RGBA")
    sx, sy = out_width / width, out_height / height
    line_width = max(2, round(min(out_width, out_height) / 350))
    for box in boxes:
        draw.rectangle(
            (
                round(box.x0 * sx), round(box.y0 * sy),
                max(round(box.x0 * sx) + 1, round(box.x1 * sx)),
                max(round(box.y0 * sy) + 1, round(box.y1 * sy)),
            ),
            fill=(255, 140, 0, 28), outline=(255, 145, 0, 255), width=line_width,
        )
    return image


def _background_rgb(array: np.ndarray) -> tuple[int, int, int]:
    value = scrap_pack._background_value(array)
    maximum = float(np.iinfo(array.dtype).max)
    if np.isscalar(value):
        channel = int(np.clip(round(float(value) * 255.0 / maximum), 0, 255))
        return channel, channel, channel
    channels = np.asarray(value).reshape(-1)
    rgb = [int(np.clip(round(float(item) * 255.0 / maximum), 0, 255)) for item in channels[:3]]
    while len(rgb) < 3:
        rgb.append(rgb[-1] if rgb else 255)
    return tuple(rgb)  # type: ignore[return-value]


def render_target(
    array: np.ndarray,
    boxes: list[scrap_pack.Box],
    placements: list[scrap_pack.Placement],
    packed_height: int,
    packed_width: int,
) -> Image.Image:
    out_width, out_height = _fit_size(packed_width, packed_height)
    scale_x, scale_y = out_width / packed_width, out_height / packed_height
    canvas = Image.new("RGB", (out_width, out_height), _background_rgb(array))
    outlines: list[tuple[int, int, int, int]] = []
    for placement in placements:
        box = boxes[placement.source_index]
        native_width = box.height if placement.rotated else box.width
        native_height = box.width if placement.rotated else box.height
        target_width = max(1, round(native_width * scale_x))
        target_height = max(1, round(native_height * scale_y))
        if placement.rotated:
            sampled = _sample_region(
                array, box.y0, box.x0, box.y1, box.x1,
                target_width, target_height,
            )
            sampled = np.rot90(sampled)
        else:
            sampled = _sample_region(
                array, box.y0, box.x0, box.y1, box.x1,
                target_height, target_width,
            )
        crop = _array_image(sampled)
        if crop.size != (target_width, target_height):
            crop = crop.resize((target_width, target_height), Image.Resampling.BOX)
        x, y = round(placement.x * scale_x), round(placement.y * scale_y)
        canvas.paste(crop, (x, y))
        outlines.append((x, y, min(out_width - 1, x + target_width - 1), min(out_height - 1, y + target_height - 1)))
    draw = ImageDraw.Draw(canvas)
    line_width = max(1, round(min(out_width, out_height) / 400))
    for rectangle in outlines:
        draw.rectangle(rectangle, outline=(255, 145, 0), width=line_width)
    return canvas


def fallback_source(path: Path) -> Image.Image | None:
    try:
        with Image.open(path) as image:
            image.seek(0)
            preview = ImageOps.exif_transpose(image).convert("RGB")
            preview.thumbnail((PANEL_WIDTH, PANEL_HEIGHT), Image.Resampling.BOX)
            return preview.copy()
    except Exception:
        return None


def _center_paste(canvas: Image.Image, panel: Image.Image, left: int, top: int) -> None:
    x = left + (PANEL_WIDTH - panel.width) // 2
    y = top + (PANEL_HEIGHT - panel.height) // 2
    canvas.paste(panel, (x, y))


def _wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, width: int, font: ImageFont.ImageFont, fill: tuple[int, int, int]) -> None:
    columns = max(20, width // 9)
    draw.multiline_text(xy, "\n".join(textwrap.wrap(text, columns)), font=font, fill=fill, spacing=4)


def assemble_overview(
    relative: Path,
    source_panel: Image.Image | None,
    target_panel: Image.Image | None,
    summary: str,
    target_message: str | None = None,
) -> Image.Image:
    width = MARGIN * 3 + PANEL_WIDTH * 2
    height = MARGIN * 3 + HEADER_HEIGHT + LABEL_HEIGHT + PANEL_HEIGHT
    canvas = Image.new("RGB", (width, height), (246, 246, 246))
    draw = ImageDraw.Draw(canvas)
    draw.text((MARGIN, MARGIN), relative.as_posix(), font=BOLD_FONT, fill=(24, 24, 24))
    _wrapped(draw, (MARGIN, MARGIN + 34), summary, width - 2 * MARGIN, SMALL_FONT, (70, 70, 70))
    panel_top = MARGIN + HEADER_HEIGHT + LABEL_HEIGHT
    left_a = MARGIN
    left_b = MARGIN * 2 + PANEL_WIDTH
    draw.text((left_a, MARGIN + HEADER_HEIGHT), "SOURCE + DETECTIONS", font=FONT, fill=(24, 24, 24))
    draw.text((left_b, MARGIN + HEADER_HEIGHT), "PACKED TARGET PREVIEW", font=FONT, fill=(24, 24, 24))
    draw.rectangle((left_a, panel_top, left_a + PANEL_WIDTH - 1, panel_top + PANEL_HEIGHT - 1), outline=(180, 180, 180))
    draw.rectangle((left_b, panel_top, left_b + PANEL_WIDTH - 1, panel_top + PANEL_HEIGHT - 1), outline=(180, 180, 180))
    if source_panel is not None:
        _center_paste(canvas, source_panel, left_a, panel_top)
    else:
        _wrapped(draw, (left_a + 24, panel_top + 40), "Source preview unavailable", PANEL_WIDTH - 48, FONT, (120, 20, 20))
    if target_panel is not None:
        _center_paste(canvas, target_panel, left_b, panel_top)
    else:
        _wrapped(draw, (left_b + 24, panel_top + 40), target_message or "No target", PANEL_WIDTH - 48, FONT, (120, 20, 20))
    return canvas


def _atomic_png(path: Path, image: Image.Image, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    info = PngImagePlugin.PngInfo()
    info.add_text("scrap_pack", json.dumps(metadata, sort_keys=True))
    try:
        image.save(temporary, format="PNG", compress_level=6, pnginfo=info)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def process_one(root: Path, output_root: Path, source: Path) -> dict[str, Any]:
    started = time.perf_counter()
    relative = source.relative_to(root)
    output = overview_path(root, output_root, source)
    cell_px, cell_reason, dpi = infer_cell_px(source, relative)
    record: dict[str, Any] = {
        "source": relative.as_posix(),
        "overview": output.relative_to(output_root).as_posix(),
        "input_bytes": source.stat().st_size,
        "cell_px": round(cell_px, 4),
        "cell_reason": cell_reason,
        "dpi": round(dpi, 3) if dpi is not None else None,
    }

    photometric = tiff_photometric(source)
    if photometric not in {None, "MINISBLACK", "RGB"}:
        detail = "CMYK/Separated" if photometric == "SEPARATED" else photometric
        record.update(
            status="unsupported",
            error=f"{detail} TIFF is outside the scrap-pack raster contract",
            photometric=photometric,
        )
        source_panel = fallback_source(source)
        overview = assemble_overview(
            relative, source_panel, None,
            f"UNSUPPORTED · {detail} TIFF · cell {cell_px:g} ({cell_reason})",
            f"UNSUPPORTED {detail}\nNo target was produced because rewriting these samples as RGB would change visual semantics.",
        )
        record["elapsed_s"] = round(time.perf_counter() - started, 4)
        _atomic_png(output, overview, record)
        record["overview_bytes"] = output.stat().st_size
        return record

    raster: scrap_pack.Raster | None = None
    try:
        load_started = time.perf_counter()
        raster = scrap_pack.load_image(source)
        load_s = time.perf_counter() - load_started
        detect_started = time.perf_counter()
        boxes = scrap_pack.detect_boxes(raster.array, cell_px=cell_px)
        detect_s = time.perf_counter() - detect_started
        pack_started = time.perf_counter()
        placements, packed_height, packed_width = scrap_pack.pack_boxes(boxes)
        pack_s = time.perf_counter() - pack_started
        source_panel = render_source(raster.array, boxes)
        target_panel = None
        target_message = "NO SEGMENTS\nNo packed target was produced."
        if boxes:
            target_panel = render_target(
                raster.array, boxes, placements, packed_height, packed_width,
            )
            target_message = None
        height, width = raster.array.shape[:2]
        canvas_pct = 100.0 * packed_height * packed_width / (height * width) if boxes else 0.0
        edge_boxes = sum(
            box.y0 == 0 or box.x0 == 0 or box.y1 == height or box.x1 == width
            for box in boxes
        )
        status = "ok" if boxes else "empty"
        summary = (
            f"{status.upper()} · {raster.array.shape} {raster.array.dtype} · "
            f"cell {cell_px:g} ({cell_reason}) · {len(boxes)} segment(s) · "
            f"packed {packed_width}×{packed_height} ({canvas_pct:.2f}% of source canvas)"
        )
        record.update(
            status=status,
            shape=list(raster.array.shape),
            dtype=str(raster.array.dtype),
            segments=len(boxes),
            packed_width=packed_width,
            packed_height=packed_height,
            canvas_pct=round(canvas_pct, 4),
            edge_boxes=edge_boxes,
            load_s=round(load_s, 4),
            detect_s=round(detect_s, 4),
            pack_s=round(pack_s, 4),
            boxes=[asdict(box) for box in boxes],
        )
        overview = assemble_overview(relative, source_panel, target_panel, summary, target_message)
    except Exception as error:
        record.update(status="error", error=f"{type(error).__name__}: {error}")
        source_panel = fallback_source(source)
        summary = f"ERROR · cell {cell_px:g} ({cell_reason}) · {record['error']}"
        overview = assemble_overview(relative, source_panel, None, summary, record["error"])
    finally:
        if raster is not None:
            mmap = getattr(raster.array, "_mmap", None)
            if mmap is not None:
                mmap.close()
    record["elapsed_s"] = round(time.perf_counter() - started, 4)
    _atomic_png(output, overview, record)
    record["overview_bytes"] = output.stat().st_size
    return record


def _read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
                records[record["source"]] = record
            except (json.JSONDecodeError, KeyError):
                continue
    return records


def write_csv(output_root: Path, records: Iterable[dict[str, Any]]) -> None:
    fields = [
        "source", "overview", "status", "input_bytes", "overview_bytes",
        "shape", "dtype", "cell_px", "cell_reason", "dpi", "segments",
        "packed_width", "packed_height", "canvas_pct", "edge_boxes",
        "load_s", "detect_s", "pack_s", "elapsed_s", "error",
    ]
    path = output_root / "manifest.csv"
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in sorted(records, key=lambda item: item["source"]):
            row = dict(record)
            row["shape"] = json.dumps(row.get("shape"))
            writer.writerow(row)
    os.replace(temporary, path)


def write_index(output_root: Path, records: Iterable[dict[str, Any]]) -> None:
    items = sorted(records, key=lambda item: item["source"])
    counts: dict[str, int] = {}
    for item in items:
        counts[item.get("status", "unknown")] = counts.get(item.get("status", "unknown"), 0) + 1
    articles: list[str] = []
    for item in items:
        source = html.escape(item["source"])
        overview = quote(item["overview"], safe="/")
        status = html.escape(item.get("status", "unknown"))
        details = html.escape(
            f"cell {item.get('cell_px', '?')} · {item.get('segments', '—')} segments · "
            f"{item.get('canvas_pct', '—')}% canvas"
        )
        articles.append(
            f'<article data-search="{source.lower()} {status}"><a href="{overview}">'
            f'<img loading="lazy" src="{overview}" alt="Overview for {source}"></a>'
            f'<div><strong>{source}</strong><br><span>{status} · {details}</span></div></article>'
        )
    summary = " · ".join(f"{key}: {value}" for key, value in sorted(counts.items()))
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Scrap-pack corpus overviews</title><style>
body{{font:14px system-ui,sans-serif;margin:20px;background:#f5f5f5;color:#222}}
header{{position:sticky;top:0;background:#f5f5f5eF;padding:0 0 12px;z-index:2}}
input{{box-sizing:border-box;width:100%;max-width:700px;padding:9px;font:inherit}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px}}
article{{background:white;border:1px solid #ccc;padding:8px;min-width:0}}
article img{{display:block;width:100%;height:auto;background:#eee}}
article div{{padding-top:7px;overflow-wrap:anywhere}} article span{{color:#555}}
</style></head><body><header><h1>Scrap-pack corpus overviews</h1>
<p>{len(items)} processed · {html.escape(summary)}</p>
<input id="filter" type="search" placeholder="Filter path or status" aria-label="Filter path or status"></header>
<main>{''.join(articles)}</main><script>
const field=document.getElementById('filter');
field.addEventListener('input',()=>{{const q=field.value.toLowerCase();document.querySelectorAll('article').forEach(a=>a.hidden=!a.dataset.search.includes(q));}});
</script></body></html>"""
    path = output_root / "index.html"
    temporary = path.with_suffix(".html.tmp")
    temporary.write_text(document, encoding="utf-8")
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("build/scrap-pack-overviews"))
    parser.add_argument("--limit", type=int, default=None, help="process only the first N frozen inputs")
    parser.add_argument("--overwrite", action="store_true", help="regenerate existing overview PNGs")
    parser.add_argument(
        "--include-admin", action="store_true",
        help="include virtual environments, caches, and .claude worktrees",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    output_root = args.output.resolve() if args.output.is_absolute() else (root / args.output).resolve()
    inputs = discover_images(root, output_root, include_admin=args.include_admin)
    if args.limit is not None:
        inputs = inputs[:max(0, args.limit)]
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "inputs.txt").write_text(
        "".join(f"{path.relative_to(root).as_posix()}\n" for path in inputs),
        encoding="utf-8",
    )
    manifest_path = output_root / "manifest.jsonl"
    existing = _read_manifest(manifest_path)
    mode = "a" if manifest_path.exists() else "w"
    completed = 0
    started = time.perf_counter()
    with manifest_path.open(mode, encoding="utf-8", buffering=1) as manifest:
        for index, source in enumerate(inputs, start=1):
            relative = source.relative_to(root).as_posix()
            target = overview_path(root, output_root, source)
            if not args.overwrite and relative in existing and target.exists() and target.stat().st_size:
                completed += 1
                continue
            record = process_one(root, output_root, source)
            manifest.write(json.dumps(record, sort_keys=True) + "\n")
            existing[relative] = record
            completed += 1
            if record["status"] in {"error", "unsupported"} or completed % 25 == 0:
                elapsed = time.perf_counter() - started
                print(
                    f"[{completed}/{len(inputs)}] {record['status']} {relative} "
                    f"({record['elapsed_s']:.2f}s; run {elapsed / 60:.1f}m)",
                    flush=True,
                )
            if completed % 100 == 0:
                write_csv(output_root, existing.values())
                write_index(output_root, existing.values())
    write_csv(output_root, existing.values())
    write_index(output_root, existing.values())
    print(
        f"complete: {completed}/{len(inputs)} inputs in {(time.perf_counter() - started) / 60:.1f}m; "
        f"index={output_root / 'index.html'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
