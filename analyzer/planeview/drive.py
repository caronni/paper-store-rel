"""`plane-view-decode`: drive the REAL receiver over the emitted planes.

Nothing here re-implements a decode.  The seams go in (`patches.install`),
`holo3.cli.main` is called in-process with an ordinary `decode` command
line, and holo3 does the rest: its own capture survey, scale-space
placement, word matching, PAVA calibration, region context, refine,
revisit, local context and the multi-capture union — the K pipeline, over
captures that hold one colour plane.

EXIT CODES.  `holo3.cli._decode` returns 2 for "NOT RECOVERED" and 0 only
when it published a verified payload.  A plane-view run never publishes
one — `--no-close` is always passed — so **2 is this harness's expected
success code** and is reported as such; 1 stays a real error (an
integrity error, a bad path, a refused `--out`).  MEASURED on the
synthetic e2e: 49/49 certificates, exit 2.

`--no-close` IS MANDATORY and is enforced here rather than left to the
operator: the plane view's fountain ESI is `counter*3 + plane`
(close.py:562), not the `counter` a one-stream unpooled row would use, so
its own close would be nonsense.  It is NOT, however, sufficient on its
own — the engine runs an incremental metadata gate whatever the close
asks for, and `patches.py`'s seventh seam is what keeps that gate
consistent.  Map the certificates back to the real cmy8 identity — the
stream id as minted, `esi = counter*3 + plane` — for any close, via
`analyzer export-facts`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .patches import install
from .row import build_plane_row

#: `holo3.cli._decode`'s "NOT RECOVERED" code — the expected outcome of
#: every plane-view run, because the close is always deferred.
EXPECTED_NO_CLOSE_CODE: int = 2


@dataclass(frozen=True)
class DecodePlan:
    """The command line the harness will run, and what it is made of."""

    plane_ref: str
    source_ref: str
    stream_id: str
    argv: tuple[str, ...]
    run_dir: Path
    out_path: Path
    seams: tuple[str, ...] = ()
    row_report: dict[str, Any] | None = None


def build_argv(plane_ref: str, scans: Sequence[Path],
               dpis: Sequence[float], *, out: Path, run_dir: Path,
               workers: int = 1, diag_port: int | None = None,
               extra: Sequence[str] = ()) -> tuple[str, ...]:
    if len(scans) != len(dpis):
        raise ValueError(
            f"exactly one --dpi per scan: {len(scans)} scans, "
            f"{len(dpis)} --dpi values")
    if not scans:
        raise ValueError("plane-view-decode needs at least one capture")
    argv: list[str] = ["decode"]
    argv.extend(str(path) for path in scans)
    for dpi in dpis:
        argv.extend(["--dpi", repr(float(dpi))])
    argv.extend(["--format", plane_ref,
                 "--out", str(out),
                 "--run-dir", str(run_dir),
                 "--workers", str(int(workers)),
                 "--no-close"])
    if diag_port is not None:
        argv.extend(["--diag", str(int(diag_port))])
    forbidden = {"--format", "--coding", "--printer", "--out", "--run-dir",
                 "--no-close", "--dpi"}
    for token in extra:
        if token.partition("=")[0] in forbidden:
            raise ValueError(
                f"pass-through option {token!r} is set by the harness")
        argv.append(str(token))
    return tuple(argv)


def plan(source_ref: str, stream_id: str, scans: Sequence[Path],
         dpis: Sequence[float], *, out: Path, run_dir: Path,
         workers: int = 1, diag_port: int | None = None,
         extra: Sequence[str] = ()) -> DecodePlan:
    """Build the row (checking the geometry claim) and the command line.

    Builds nothing in holo3 and patches nothing — this is the dry run.
    """
    plane_row, source_row, report = build_plane_row(source_ref, stream_id)
    argv = build_argv(plane_row.row_id, scans, dpis, out=out,
                      run_dir=run_dir, workers=workers,
                      diag_port=diag_port, extra=extra)
    return DecodePlan(plane_ref=plane_row.row_id,
                      source_ref=source_row.row_id,
                      stream_id=stream_id, argv=argv, run_dir=Path(run_dir),
                      out_path=Path(out), row_report=report)


def run(source_ref: str, stream_id: str, scans: Sequence[Path],
        dpis: Sequence[float], *, out: Path, run_dir: Path,
        workers: int = 1, diag_port: int | None = None,
        extra: Sequence[str] = (), manifest: Path | None = None) -> int:
    """Install the seams, call `holo3.cli.main`, restore, return its code."""
    from holo3 import cli as h3_cli

    plane_row, source_row, report = build_plane_row(source_ref, stream_id)
    decode_plan = DecodePlan(
        plane_ref=plane_row.row_id, source_ref=source_row.row_id,
        stream_id=stream_id,
        argv=build_argv(plane_row.row_id, scans, dpis, out=out,
                        run_dir=run_dir, workers=workers,
                        diag_port=diag_port, extra=extra),
        run_dir=Path(run_dir), out_path=Path(out), row_report=report)
    installation = install(plane_row, source_row)
    if manifest is not None:
        Path(manifest).parent.mkdir(parents=True, exist_ok=True)
        Path(manifest).write_text(json.dumps({
            "plane_view_ref": decode_plan.plane_ref,
            "source_ref": decode_plan.source_ref,
            "stream_id": stream_id,
            "argv": list(decode_plan.argv),
            "row": report,
            "seams": list(installation.seams),
            "esi_note": ("plane-view certificates map back as stream "
                         f"{stream_id!r}, esi = counter*3 + "
                         f"{installation.plane_index}"),
        }, indent=2, sort_keys=True), "utf-8")
    try:
        return int(h3_cli.main(list(decode_plan.argv)))
    finally:
        installation.uninstall()
