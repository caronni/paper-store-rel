#!/usr/bin/env python
"""Persistent multi-scan E021 -> E022 pilot-placement session.

Each invocation folds one or more independent scans into an atomic local
state. The state retains every scan's placement poses and pilot observations;
it does not average source coordinates across scans. The combined pilot map is
recomputed from those immutable per-scan records after every ingest.

Recommended native footing:

  env/bin/python experiments/022-pilot-tile-search/session_e022.py \
      scan-1.tiff --dpi 4800 --diag

Run the same command later with another TIFF. By default the state lives at
``experiments/022-pilot-tile-search/build/session_state.pkl``. Use ``--fresh``
to start a new session or ``--state`` to maintain several sessions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from paperholo import (  # noqa: E402
    formats,
    pilotcombine,
    pilotdiag,
    pilotsearch,
    platen,
)

# 3 = v2.2 pilotsearch (redundant placements recorded with full poses for
# E023 payload sampling). v2 states lack those poses — an incomplete input
# for the payload pass — and refuse cleanly on the version check, as v1
# object pickles do.
STATE_VERSION = 3
DEFAULT_STATE = HERE / "build" / "session_state.pkl"
DEFAULT_OUT = HERE / "build" / "session_e022.png"
DEFAULT_DIAG = HERE / "build" / "session_diag"

Image.MAX_IMAGE_PIXELS = None


@dataclass
class SessionScan:
    scan_id: str
    source_path: str
    source_sha256: str
    source_size: int
    dpi: float
    region_count: int
    c_dots: int | None
    cell_pitch_px: float | None
    angle_hints: int
    result: pilotsearch.SearchResult


@dataclass
class E022Session:
    version: int
    format_id: str
    seed: bytes
    cell_dots: int
    page_cells_yx: tuple[int, int]
    pages: tuple[int, ...]
    dpi: float
    scans: list[SessionScan] = field(default_factory=list)


def _new_session(descriptor, pages: tuple[int, ...], dpi: float) -> E022Session:
    spec = descriptor.spec()
    return E022Session(
        version=STATE_VERSION,
        format_id=descriptor.format_id,
        seed=descriptor.seed,
        cell_dots=descriptor.cell_dots,
        page_cells_yx=tuple(spec.page_cells_yx),
        pages=pages,
        dpi=float(dpi),
    )


def _validate_session(session: E022Session, descriptor,
                      pages: tuple[int, ...], dpi: float) -> None:
    spec = descriptor.spec()
    expected = (
        STATE_VERSION, descriptor.format_id, descriptor.seed,
        descriptor.cell_dots, tuple(spec.page_cells_yx), pages, float(dpi),
    )
    actual = (
        session.version, session.format_id, session.seed, session.cell_dots,
        tuple(session.page_cells_yx), tuple(session.pages), float(session.dpi),
    )
    if actual != expected:
        raise ValueError(
            "state format/pages/dpi mismatch; pass --fresh or choose another "
            "--state path"
        )


def load_session(path: Path, descriptor, pages: tuple[int, ...], dpi: float,
                 *, fresh: bool = False) -> E022Session:
    if fresh or not path.exists():
        return _new_session(descriptor, pages, dpi)
    payload = pickle.loads(path.read_bytes())
    if not isinstance(payload, dict) or payload.get("magic") != "e022-session-v1":
        raise ValueError(f"{path} is not an E022 session state")
    try:
        loaded = E022Session(
            version=int(payload["version"]),
            format_id=str(payload["format_id"]),
            seed=bytes(payload["seed"]),
            cell_dots=int(payload["cell_dots"]),
            page_cells_yx=tuple(payload["page_cells_yx"]),
            pages=tuple(payload["pages"]),
            dpi=float(payload["dpi"]),
            scans=[SessionScan(**row) for row in payload["scans"]],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{path} has an invalid E022 state schema") from exc
    _validate_session(loaded, descriptor, pages, dpi)
    return loaded


def save_session(path: Path, session: E022Session) -> None:
    """Atomically replace a state only after a complete scan is ingested."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "magic": "e022-session-v1",
        "version": session.version,
        "format_id": session.format_id,
        "seed": session.seed,
        "cell_dots": session.cell_dots,
        "page_cells_yx": session.page_cells_yx,
        "pages": session.pages,
        "dpi": session.dpi,
        "scans": [scan.__dict__ for scan in session.scans],
    }
    tmp.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, path)


def file_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def load_image(path: Path) -> np.ndarray:
    """Load one scan without depending on the single-scan CLI module."""
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


def _iter_results(session: E022Session, current=None):
    for scan in session.scans:
        yield pilotcombine.SearchResultPart(
            scan.scan_id, scan.region_count, scan.result
        )
    if current is not None:
        yield pilotcombine.SearchResultPart(*current)


def combine_results(
    session: E022Session,
    descriptor,
    *,
    current: tuple[str, int, pilotsearch.SearchResult] | None = None,
    decode_words: bool = True,
) -> pilotsearch.SearchResult:
    """Compatibility wrapper around the shared pure combiner."""
    return pilotcombine.combine_search_results(
        _iter_results(session, current),
        descriptor,
        pages=session.pages,
        decode_words=decode_words,
    )


def _scan_summary(scan: SessionScan) -> dict:
    return {
        "scan_id": scan.scan_id,
        "source_path": scan.source_path,
        "source_sha256": scan.source_sha256,
        "source_size": scan.source_size,
        "dpi": scan.dpi,
        "survey": {
            "regions": scan.region_count,
            "c_dots": scan.c_dots,
            "cell_pitch_px": scan.cell_pitch_px,
            "angle_hints": scan.angle_hints,
        },
        "placements": len(scan.result.placements),
        "pilot_tiles": len(scan.result.tiles),
        "timings": scan.result.timings,
    }


def session_report(session: E022Session, descriptor,
                   combined: pilotsearch.SearchResult) -> dict:
    return {
        "state_version": session.version,
        "format_id": session.format_id,
        "pages": list(session.pages),
        "dpi": session.dpi,
        "scans": [_scan_summary(scan) for scan in session.scans],
        "combined": pilotdiag.search_result_report(combined, descriptor),
    }


def _json_default(value):
    return pilotdiag.json_default(value)


def save_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(
        report, indent=2, sort_keys=True, default=_json_default
    ) + "\n")
    os.replace(tmp, path)


def _counts(result: pilotsearch.SearchResult) -> dict[str, int]:
    return {
        "placements": len(result.placements),
        "redundant": sum(
            getattr(row, "redundant", False) for row in result.placements
        ),
        "tiles": len(result.tiles),
        "bch_matching": sum(tile.bch_ok is True for tile in result.tiles.values()),
        "bch_contradictory": sum(tile.bch_ok is False for tile in result.tiles.values()),
        "bch_refused": sum(tile.bch_refused for tile in result.tiles.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--dpi", type=float, required=True,
                        help="true input DPI; use 4800 for native Canon scans")
    parser.add_argument("--format", default="e018-v3-c3")
    parser.add_argument("--pages", default="0",
                        help="comma-separated legal page numbers")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--diag", nargs="?", const=str(DEFAULT_DIAG),
                        default=None, metavar="DIR",
                        help="serve an auto-refreshing localhost view and "
                             "write numbered PNG frames")
    parser.add_argument("--diag-port", type=int, default=8022)
    parser.add_argument("--no-bch-first", action="store_true")
    args = parser.parse_args()

    descriptor = resolve_format(args.format)
    pages = tuple(int(value) for value in args.pages.split(","))
    try:
        session = load_session(
            args.state, descriptor, pages, args.dpi, fresh=args.fresh
        )
    except (ValueError, pickle.UnpicklingError, EOFError) as exc:
        print(f"state error: {exc}", file=sys.stderr)
        return 2

    diag = None
    if args.diag is not None:
        try:
            import e022_diag as diag_mod
            diag = diag_mod.DiagViewer(Path(args.diag), args.diag_port)
        except OSError as exc:
            print(f"  [diag] unavailable: {exc!r}; session continues",
                  flush=True)
    report_path = args.report or args.out.with_suffix(".json")
    known_hashes = {scan.source_sha256 for scan in session.scans}
    config = pilotsearch.SearchConfig(bch_first=not args.no_bch_first)
    try:
        for image_path in args.images:
            source_sha, source_size = file_sha256(image_path)
            if source_sha in known_hashes:
                print(f"{image_path}: already ingested ({source_sha[:12]}) -- skip")
                continue
            scan_id = f"s{len(session.scans):03d}"
            image = load_image(image_path)
            print(f"{scan_id} E021: {image_path} {image.shape} dpi={args.dpi:g}",
                  flush=True)
            survey = platen.detect_payload_regions(image, dpi=args.dpi)
            print(f"  regions={len(survey.regions)} c={survey.c_dots} "
                  f"pitch={survey.cell_pitch_px}", flush=True)
            current = pilotsearch.SearchResult()

            def publish(result, region_index=None, *, include_current=True):
                if diag is None:
                    return
                try:
                    reference = combine_results(
                        session, descriptor,
                        current=((scan_id, len(survey.regions), result)
                                 if include_current else None),
                        decode_words=not include_current,
                    )
                    png = pilotdiag.diagnostic_png_bytes(
                        image, survey, result, descriptor,
                        reference_result=reference,
                        active_region=region_index,
                    )
                    meta = _counts(reference)
                    meta.update({
                        "scan": image_path.name,
                        "scan_id": scan_id,
                        "scans": len(session.scans) + (
                            1 if include_current else 0
                        ),
                        "regions_done": len(result.region_states),
                        "regions": len(survey.regions),
                    })
                    diag.publish(png, meta)
                except Exception as exc:  # diagnostics are an observer
                    diag.disable(exc)

            publish(current)

            def on_region(result, region_index):
                state = result.region_states[region_index]
                n_placements = sum(
                    row.region_index == region_index
                    for row in result.placements
                )
                print(f"  region {region_index}: {state}, "
                      f"placements={n_placements}", flush=True)
                publish(result, region_index)

            current = pilotsearch.search_survey(
                image, survey, descriptor, pages=pages, config=config,
                scan_id=scan_id, scan_dpi=args.dpi, on_region=on_region,
            )
            scan = SessionScan(
                scan_id=scan_id,
                source_path=str(image_path.resolve()),
                source_sha256=source_sha,
                source_size=source_size,
                dpi=float(args.dpi),
                region_count=len(survey.regions),
                c_dots=survey.c_dots,
                cell_pitch_px=survey.cell_pitch_px,
                angle_hints=sum(
                    region.angle_hint_deg is not None
                    for region in survey.regions
                ),
                result=current,
            )
            session.scans.append(scan)
            known_hashes.add(source_sha)
            save_session(args.state, session)
            combined = combine_results(session, descriptor)
            save_report(
                report_path, session_report(session, descriptor, combined)
            )
            try:
                pilotdiag.render_diagnostic(
                    image, survey, current, descriptor, args.out,
                    reference_result=combined,
                )
            except Exception as exc:
                print(f"  PNG observer failed: {exc!r}; state is committed",
                      flush=True)
            publish(current, include_current=False)
            counts = _counts(combined)
            print(f"  committed {scan_id}: session scans={len(session.scans)} "
                  f"placements={counts['placements']} tiles={counts['tiles']} "
                  f"BCH={counts['bch_matching']}/"
                  f"{counts['bch_contradictory']}/"
                  f"{counts['bch_refused']}", flush=True)
            print(f"  state {args.state}\n  PNG {args.out}\n  JSON {report_path}",
                  flush=True)
    finally:
        if diag is not None:
            diag.close()

    combined = combine_results(session, descriptor)
    counts = _counts(combined)
    print(f"E022 session: scans={len(session.scans)} "
          f"placements={counts['placements']} tiles={counts['tiles']} "
          f"BCH matching/contradictory/refused="
          f"{counts['bch_matching']}/{counts['bch_contradictory']}/"
          f"{counts['bch_refused']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
