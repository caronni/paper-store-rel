#!/usr/bin/env python
"""E023 payload-tile decoding driver: e022 v2.2 state + original scans in,
CRC-certified LDPC tiles + honest per-tile report out.

  env/bin/python experiments/023-payload-tiles/run_e023.py \
      --e022-state <022's build>/session_state.pkl \
      --state build/e023_decimated.pkl

  env/bin/python experiments/023-payload-tiles/run_e023.py \
      --e022-state .../session_state.pkl --state build/e023_decimated.pkl \
      --diag build/session_diag

Persistence seam (round 4): --e022-state is the read-only upstream input;
--state is e023's own resumable pickle. Resume = unchanged-prefix +
append-only against the upstream fingerprint; any upstream mutation or
reordering requires --fresh. The PNG is page-space only (placements /
pilot map / LDPC tile map) — the scan-space view belongs to e022.

``--diag [DIR]`` serves a localhost auto-refreshing three-pane view and
writes numbered PNG frames after each ingested scan (+ one union frame).
The hook is a read-only observer — decode state is byte-identical with
the flag off (``tests/test_e023_diag.py``).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/022-pilot-tile-search"))

from paperholo import ldpc, payloaddec  # noqa: E402
from paperholo.formats import FORMAT_REGISTRY  # noqa: E402
import run_e022  # noqa: E402  (page-space panel reuse)
import session_e022  # noqa: E402  (combined SearchResult for panes A/B)

DEFAULT_STATE = HERE / "build" / "e023_state.pkl"
DEFAULT_DIAG = HERE / "build" / "session_diag"

TILE_COLORS = {
    "certified": (98, 190, 110),
    "attempted_failed": (214, 69, 60),
    "below_attempt_floor": (245, 190, 96),
    "unobserved": (233, 233, 233),
    "degenerate": (170, 170, 185),
}


def ldpc_panel(state: payloaddec.DecodeState, *, width: int,
               page: int = 0) -> Image.Image:
    spec = state.spec
    h, w = spec.page_cells_yx
    height = max(1, int(round(width * h / w)))
    panel = Image.new("RGB", (width, height), (246, 246, 242))
    draw = ImageDraw.Draw(panel)
    scale = width / w
    tc = ldpc.TILE_CELLS
    states = payloaddec.full_tile_states(state)
    for (pg, ty, tx), tile_state in states.items():
        if pg != page:
            continue
        color = TILE_COLORS[tile_state]
        x0, y0 = tx * tc * scale, ty * tc * scale
        x1 = min(w, (tx + 1) * tc) * scale
        y1 = min(h, (ty + 1) * tc) * scale
        draw.rectangle((x0, y0, x1, y1), fill=color, outline=(252, 252, 252))
    counts: dict[str, int] = {}
    for (pg, _, _), tile_state in states.items():
        if pg == page:
            counts[tile_state] = counts.get(tile_state, 0) + 1
    title = ("D  LDPC tiles: " + " ".join(
        f"{key}={counts.get(key, 0)}"
        for key in ("certified", "attempted_failed", "below_attempt_floor",
                    "unobserved", "degenerate")))
    return run_e022._panel_title(panel, title)


def compose_diagnostic(state: payloaddec.DecodeState, combined,
                       descriptor, *, panel_width: int = 720) -> Image.Image:
    """Three page-space panes: placements / pilot map / LDPC tile map."""
    spec = descriptor.spec()
    panels = [
        run_e022.placement_panel(combined, spec, width=panel_width),
        run_e022.pilot_panel(combined, spec, width=panel_width),
        ldpc_panel(state, width=panel_width),
    ]
    height = max(p.height for p in panels)
    canvas = Image.new("RGB", (sum(p.width for p in panels), height),
                       (255, 255, 255))
    x = 0
    for p in panels:
        canvas.paste(p, (x, 0))
        x += p.width
    return canvas


def diagnostic_png_bytes(state: payloaddec.DecodeState, combined,
                         descriptor, *, panel_width: int = 720) -> bytes:
    canvas = compose_diagnostic(state, combined, descriptor,
                                panel_width=panel_width)
    stream = io.BytesIO()
    canvas.save(stream, format="PNG")
    return stream.getvalue()


def render_png(state: payloaddec.DecodeState, combined, descriptor,
               out: Path, *, panel_width: int = 720) -> Path:
    canvas = compose_diagnostic(state, combined, descriptor,
                                panel_width=panel_width)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def diag_meta(state: payloaddec.DecodeState, *, step: str,
              scans_done: int, scans_total: int) -> dict:
    """Status line fields for ``e023_diag.DiagViewer``."""
    tiles = state.summary()["tiles"]
    return {
        "step": step,
        "scans_done": scans_done,
        "scans_total": scans_total,
        "certified": int(tiles.get("certified", 0)),
        "attempted_failed": int(tiles.get("attempted_failed", 0)),
        "below_attempt_floor": int(tiles.get("below_attempt_floor", 0)),
        "unobserved": int(tiles.get("unobserved", 0)),
        "degenerate": int(tiles.get("degenerate", 0)),
        "user_bits": int(state.summary()["certified_user_bits"]),
        "attempts": int(state.n_attempts),
    }


def report_dict(state: payloaddec.DecodeState) -> dict:
    tiles = []
    for key in sorted(state.tiles):
        out = state.tiles[key]
        tiles.append({
            "page_tile": list(key),
            "state": out.state,
            "certified_by": out.certified_by,
            "k_eff": out.k_eff,
            "n_informative_best": out.n_informative_best,
            "n_nonshort": out.n_nonshort,
            "n_iters": out.n_iters,
            "attempts": out.attempts,
            "n_user_bits": (0 if out.user_bits is None
                            else int(out.user_bits.size)),
            "divergence": out.divergence,
        })
    return {
        "format_id": state.format_id,
        "rate_id": state.rate_id,
        "pages": list(state.pages),
        "upstream": [list(row) for row in state.upstream],
        "summary": state.summary(),
        "scans": [{
            "scan_id": s.scan_id,
            "windows": s.window_rows,
            "payload_cells": {int(p): int(v["index"].size)
                              for p, v in s.pages.items()},
        } for s in state.scans],
        "tiles": tiles,
    }


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _as_e022_session_obj(session: payloaddec.E022Session):
    """Adapter: payloaddec's frozen view -> session_e022.combine_results
    input (which needs .scans[i].{scan_id,region_count,result})."""
    class _Scan:
        def __init__(self, s):
            self.scan_id = s.scan_id
            self.result = s.result
            self.region_count = (
                max((p.region_index for p in s.result.placements),
                    default=-1) + 1)

    class _Session:
        def __init__(self, s):
            self.scans = [_Scan(row) for row in s.scans]
            self.pages = list(s.pages)

    return _Session(session)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--e022-state", type=Path, required=True,
                        help="read-only upstream e022 v2.2 session pickle")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--rate", default=None,
                        help="EXPERIMENTAL override; default = the format "
                             "registry row's ldpc_rate")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--diag", nargs="?", const=str(DEFAULT_DIAG),
                        default=None, metavar="DIR",
                        help="serve an auto-refreshing localhost view and "
                             "write numbered PNG frames per ingested scan")
    parser.add_argument("--diag-port", type=int, default=8023)
    args = parser.parse_args()

    try:
        session = payloaddec.load_e022_session(args.e022_state)
    except (ValueError, payloaddec.FatalIntegrityError) as exc:
        print(f"e022 state error: {exc}", file=sys.stderr)
        return 2
    descriptor = next(f for f in FORMAT_REGISTRY
                      if f.format_id == session.format_id)
    print(f"e022 session: {len(session.scans)} scans, format "
          f"{session.format_id}, pages {list(session.pages)}", flush=True)

    state = None
    if not args.fresh and args.state.exists():
        try:
            state = payloaddec.load_state(args.state, descriptor)
            print(f"resuming {args.state} "
                  f"({len(state.scans)} scans ingested)", flush=True)
        except ValueError as exc:
            print(f"state error: {exc}", file=sys.stderr)
            return 2

    e022_view = _as_e022_session_obj(session)
    combined = session_e022.combine_results(
        e022_view, descriptor, decode_words=False)
    scans_total = len(session.scans)
    scans_done = len(state.scans) if state is not None else 0

    diag = None
    if args.diag is not None:
        try:
            import e023_diag as diag_mod
            diag = diag_mod.DiagViewer(Path(args.diag), args.diag_port)
        except OSError as exc:
            print(f"  [diag] unavailable: {exc!r}; session continues",
                  flush=True)

    def publish_diag(st: payloaddec.DecodeState, step: str,
                     scans_done_now: int) -> None:
        if diag is None:
            return
        try:
            png = diagnostic_png_bytes(st, combined, descriptor)
            meta = diag_meta(st, step=step, scans_done=scans_done_now,
                             scans_total=scans_total)
            diag.publish(png, meta)
        except Exception as exc:
            diag.disable(exc)

    if state is not None and scans_done > 0:
        publish_diag(state, f"resume ({scans_done} scans)", scans_done)

    def on_scan(st, scan_id, counts, elapsed):
        nonlocal scans_done
        summary = st.summary()["tiles"]
        print(f"  {scan_id}: attempted={counts['attempted']} "
              f"certified+={counts['certified']} "
              f"(total certified={summary.get('certified', 0)}) "
              f"[{elapsed:.1f}s]", flush=True)
        if scan_id != "union":
            scans_done += 1
            payloaddec.save_state(args.state, st)
        publish_diag(st, scan_id, scans_done)

    try:
        state = payloaddec.run_session(session, descriptor,
                                       rate_id=args.rate, state=state,
                                       on_scan=on_scan)
    except payloaddec.FatalIntegrityError as exc:
        print(f"FATAL integrity violation: {exc}", file=sys.stderr)
        if diag is not None:
            diag.close()
        return 3
    payloaddec.save_state(args.state, state)

    out_png = args.out or HERE / "build" / (args.state.stem + ".png")
    report_path = args.report or out_png.with_suffix(".json")
    render_png(state, combined, descriptor, out_png)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = report_path.with_suffix(report_path.suffix + ".tmp")
    tmp.write_text(json.dumps(report_dict(state), indent=2, sort_keys=True,
                              default=_json_default) + "\n")
    os.replace(tmp, report_path)

    summary = state.summary()
    print(f"e023: tiles {summary['tiles']}  user_bits="
          f"{summary['certified_user_bits']}  attempts="
          f"{summary['n_attempts']} (CRC budget "
          f"{summary['crc_false_accept_budget']:.2e})  divergence mean/max "
          f"{summary['divergence_mean']}/{summary['divergence_max']}")
    print(f"  state {args.state}\n  PNG {out_png}\n  JSON {report_path}")
    if diag is not None:
        diag.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
