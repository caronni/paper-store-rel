from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
from pathlib import Path

from . import data, engine, schedule
from .format import identity


class _Parser(argparse.ArgumentParser):

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(1)


def _build_parser() -> _Parser:
    parser = _Parser(prog="holo3")
    commands = parser.add_subparsers(dest="command", required=True)
    decode = commands.add_parser("decode")
    decode.add_argument("scans", nargs="+", type=Path)
    decode.add_argument("--dpi", action="append", type=float, default=[])
    decode.add_argument("--format", dest="format_ref")
    decode.add_argument("--coding")
    decode.add_argument("--printer")
    decode.add_argument("--max-pages", dest="max_pages", type=int,
                        default=None)
    decode.add_argument("--out", type=Path, required=True)
    decode.add_argument("--workers", type=int, default=1)
    decode.add_argument("--complete", action="store_true")
    decode.add_argument("--no-close", dest="no_close", action="store_true")
    decode.add_argument("--no-pooled-color-context",
                        dest="pooled_color_context", action="store_false")
    decode.add_argument("--plane-fields", dest="plane_fields",
                        action="store_true")
    decode.add_argument("--diag", type=int, metavar="PORT")
    decode.add_argument("--run-dir", dest="run_dir", type=Path)
    decode.add_argument("--resume", type=Path, metavar="STATE_FILE")
    decode.add_argument("--snapshot-every", dest="snapshot_every_min",
                        type=float, default=30.0, metavar="MINUTES",
                        help="safety facts.npz cadence (0 = off); SIGUSR1 "
                             "dumps on demand, ctrl-T prints status")
    schedule = commands.add_parser("schedule")
    schedule.add_argument("--format", dest="format_ref")
    return parser


def _format_ref(args: argparse.Namespace) -> str:
    if args.format_ref is not None:
        if args.coding is not None or args.printer is not None:
            raise ValueError(
                "--format and --coding/--printer are exclusive routes")
        return str(args.format_ref)
    if args.coding is None or args.printer is None:
        raise ValueError(
            "format identity required: --format REF, or both "
            "--coding ID and --printer ID")
    try:
        return identity.coding_printer_ref(args.coding, args.printer)
    except KeyError as exc:
        raise ValueError(
            f"unknown --coding/--printer identity: {exc}")


def run_dir_for(base: Path) -> Path:
    return base.with_name(f"{base.name}.{os.getpid()}")


def _request(args: argparse.Namespace) -> engine.DecodeRequest:
    if len(args.dpi) != len(args.scans):
        raise ValueError(
            f"exactly one --dpi per scan: {len(args.scans)} scans, "
            f"{len(args.dpi)} --dpi values")
    dpis = tuple(float(value) for value in args.dpi)
    for scan, dpi in zip(args.scans, dpis):
        if not math.isfinite(dpi) or dpi <= 0:
            raise ValueError(
                f"declared --dpi {dpi} for {scan} must be finite and "
                f"positive")
    if args.out.exists():
        raise ValueError(f"refusing to overwrite existing --out {args.out}")
    if args.workers < 1:
        raise ValueError(f"--workers {args.workers} must be >= 1")
    format_ref = _format_ref(args)
    row = identity.resolve_format_ref(format_ref)
    if args.max_pages is not None:
        if args.max_pages < 1:
            raise ValueError(f"--max-pages {args.max_pages} must be >= 1")
        if args.max_pages > row.max_pages:
            raise ValueError(
                f"--max-pages {args.max_pages} exceeds "
                f"{row.max_pages} possible")
    run_dir = (run_dir_for(args.run_dir) if args.run_dir is not None
               else Path(tempfile.mkdtemp(prefix="holo3-")))
    return engine.DecodeRequest(
        scans=tuple(args.scans),
        dpis=dpis,
        format_ref=format_ref,
        max_pages=args.max_pages,
        workers=args.workers,
        complete=bool(args.complete),
        no_close=bool(args.no_close),
        diag_port=args.diag,
        run_dir=run_dir,
        pooled_color_context=bool(args.pooled_color_context),
        plane_fields=bool(args.plane_fields),
        resume=args.resume,
        snapshot_every_s=(float(args.snapshot_every_min) * 60.0
                          if args.snapshot_every_min and
                          args.snapshot_every_min > 0 else None))


def _status_rows(events: list[data.Event],
                 result: data.RunResult) -> tuple[str, ...]:
    try:
        from .diag import model, readout

        folded = model.fold(model.empty(), events)
        rows = list(readout.all_rows(folded))
        splits = readout.plane_cert_counts(folded)
        if len(splits) > 1:
            joined = " · ".join(f"{stream}:{count}"
                                for stream, count in splits)
            rows.append(f"planes   certified [{joined}]")
        shortfall = readout.close_shortfall_line(folded)
        if shortfall is not None:
            rows.append(f"needs    {shortfall}")
        churn = readout.churn_advisory(folded)
        if churn is not None:
            rows.append(f"churn    {churn}")
        isolation = readout.ladder_isolation_advisory(folded)
        if isolation is not None:
            rows.append(f"ladder   {isolation}")
        return tuple(rows)
    except Exception:
        return (f"status   {result.status}",
                f"tiles    CERTIFIED {result.certified}")


def _accounting_table(result: data.RunResult) -> tuple[str, ...]:
    header = (f"{'plugin':<12} {'jobs':>6} {'cpu_s':>9} {'certs':>6} "
              f"{'poses':>6} {'words':>6}")
    lines = [header]
    for row in result.plugin_rows:
        lines.append(
            f"{row.plugin:<12} {row.jobs:>6} {row.cpu_seconds:>9.2f} "
            f"{row.certificates:>6} {row.poses:>6} {row.words:>6}")
    return tuple(lines)


def _publish_payload(out_path: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{out_path.name}.", suffix=".tmp", dir=out_path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, out_path)
        directory = os.open(out_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError:
        raise ValueError(
            f"refusing to overwrite existing payload: {out_path}")
    except OSError as exc:
        raise ValueError(
            f"could not write recovered payload {out_path}: {exc}")
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _decode(args: argparse.Namespace) -> int:
    events: list[data.Event] = []
    try:
        request = _request(args)
        result = engine.decode(request, events)
    except data.IntegrityError as exc:
        print(f"holo3: integrity error: {exc}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(f"holo3: {exc}", file=sys.stderr)
        return 1
    for line in _status_rows(events, result):
        print(line, file=sys.stderr)
    for line in _accounting_table(result):
        print(line, file=sys.stderr)
    print(f"run dir: {request.run_dir}", file=sys.stderr)
    if result.status == "verified" and result.payload is not None:
        try:
            _publish_payload(args.out, result.payload)
        except ValueError as exc:
            print(f"holo3: {exc}", file=sys.stderr)
            return 1
        print(f"VERIFIED {len(result.payload)} bytes "
              f"sha256 {result.payload_sha256}")
        return 0
    print(f"NOT RECOVERED — status {result.status}, "
          f"{result.certified} certificates", file=sys.stderr)
    return 2


def _schedule(args: argparse.Namespace) -> int:
    row = None
    if args.format_ref is not None:
        try:
            row = identity.resolve_format_ref(str(args.format_ref))
        except (KeyError, ValueError) as exc:
            print(f"holo3: unknown --format: {exc}", file=sys.stderr)
            return 1
    for line in schedule.render(engine.DESCRIPTORS, row):
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "schedule":
        return _schedule(args)
    return _decode(args)
