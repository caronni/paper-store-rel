"""The holo CLI: registry | fit | capacity | generate | decode | discover.

Generation is the production surface here.  ``decode`` is a door: since the v1
receiver's retirement (2026-09-05) it forwards its argument vector to holo3's
CLI, which owns receiving; ``./confetti3.py decode`` is the explicit spelling.
Invocation (no console script — the venv stays clean):

    ./confetti.py <cmd> ...                   # repo-root wrapper
    env/bin/python src/holo/cli.py <cmd> ...
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

if __package__ in (None, ""):   # executed as a file: put src/ on the path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from holo.cli_gen import (
    _SOURCE_FRACTION_HELP,
    cmd_capacity,
    cmd_fit,
    cmd_generate,
    cmd_registry,
)
from holo.gen.sheet import DEFAULT_ENGINE_DPI, DEFAULT_PAPER, PAPER_PROFILES



def _finite_nonnegative(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return parsed


def _engine_dpi(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive dpi")
    return parsed


def _decode_door_parser() -> argparse.ArgumentParser:
    """`decode --help` is answered here, never by holo3: an operator who
    typed the v1 spelling has to be told where the old flags went before
    holo3's own list is any use to them."""
    return argparse.ArgumentParser(
        prog="holo decode",
        usage="holo decode SCAN [SCAN ...] --dpi DPI [--dpi DPI ...]\n"
              "                   (--format ID | --coding ID --printer ID)"
              " --out FILE [holo3 option ...]",
        description=(
            "Recover a payload from scans of printed sheets.\n"
            "\n"
            "Every argument after `decode` is forwarded verbatim to the "
            "holo3 receiver\n"
            "(src/holo/receiver/cli.py) — the same entry `./confetti3.py decode` uses, "
            "and the\n"
            "explicit spelling to prefer in scripts.\n"
            "\n"
            "The v1 receiver this command used to drive was retired on "
            "2026-09-05 and\n"
            "its options went with it: declare scan resolution with --dpi "
            "(not\n"
            "--scan-dpi), resume with --resume STATE_FILE — holo3's fact "
            "snapshot,\n"
            "there is no --state — and serve the live view with --diag PORT "
            "(no\n"
            "--diag-dir/--diag-interval/--diag-panel-width). --mopup, "
            "--refine and\n"
            "--profile-timing have no holo3 spelling: holo3 schedules its "
            "own ladder.\n"
            "Discovery-first decoding (neither --coding nor --format) went "
            "with the v1\n"
            "receiver too — name the format."),
        epilog=("holo3's own option list: ./confetti3.py decode --help\n"
                "registry | fit | capacity | generate | discover are "
                "unchanged and still run here."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False)


def cmd_decode(argv: list[str]) -> int:
    """Hand the rest of argv to holo3's CLI (Gate E brief §3 step 2,
    2026-09-05: the v1 receiver is deleted).  The split is taken on argv at
    the verb rather than through an argparse.REMAINDER positional because
    REMAINDER refuses a leading option: `decode --format X scan.tiff` would
    die with a holo1 parse error naming a holo3 flag."""
    if argv[:1] in (["-h"], ["--help"]):
        _decode_door_parser().print_help()
        return 0
    # holo3 lives beside src/, not inside it, so put the repo root on the
    # path the way confetti3.py does — the forward then works however this
    # module was reached (./confetti.py, `python -m holo.cli`, the file).
    from holo.receiver.cli import main as holo3_main

    return holo3_main(["decode", *argv])


def main(argv: list[str] | None = None) -> int:
    effective_argv = sys.argv[1:] if argv is None else list(argv)
    if effective_argv and effective_argv[0] == "discover":
        # Characterization is an isolated instrument.  This composition-root
        # import exposes it without coupling generator, receiver, format, or
        # device-library code to its implementation.
        from holo.characterize.__main__ import main as characterize_main

        return characterize_main(
            effective_argv[1:], prog="holo discover"
        )
    if effective_argv and effective_argv[0] == "decode":
        # 2026-09-05 (Gate E brief §3 step 2): receiving belongs to holo3.
        # Intercepted here beside `discover` so that no holo1 parser stands
        # between the operator and holo3's own options and errors.
        return cmd_decode(effective_argv[1:])

    ap = argparse.ArgumentParser(
        prog="holo",
        description="Store files on plain printed paper. `fit` sizes a "
                    "field for a sheet; `capacity` plans volumes; "
                    "`generate` writes printable PostScript; "
                    "`decode` forwards scans to the holo3 receiver; "
                    "`discover` characterizes a print/scan path.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_selection(p: argparse.ArgumentParser) -> None:
        p.add_argument("--format", metavar="ID",
                       help="the printed format, in full: "
                            "PITCH-FAMILY[-RUNGS][-pSITES][-vGEN]@TYxTX "
                            "(e.g. c2-k-r0700@53x37, "
                            "c2-cmy8-r0700@53x37; `fit` derives the "
                            "matrix for a paper), or a legacy L: fossil "
                            "(e.g. L:c2-r0700@3392x2368), which carries "
                            "its own page. Requires --source-fraction")
        p.add_argument("--paper", metavar="NAME", default=None,
                       help="paper bundle for a v2 --format field: "
                            + " | ".join(sorted(PAPER_PROFILES))
                            + f" (default {DEFAULT_PAPER})")
        p.add_argument("--dpi", type=_engine_dpi, metavar="N", default=None,
                       help="engine dot grid for a v2 --format field "
                            f"(default {DEFAULT_ENGINE_DPI}, the only "
                            "measured class); pitch x dpi must be a whole "
                            "number of dots per cell")
        p.add_argument("--printer", default=None, metavar="ENGINE",
                       help="the emission engine (a `registry` printer "
                            "id): its record selects how colour is asked "
                            "of it (cmyk1 composite or rgb single-toner "
                            "masks), never a geometry; unnamed = cmyk1; "
                            "an engine without a colour record refuses a "
                            "colour format. holo3's `decode --printer` is "
                            "its own legacy door, not this")
        p.add_argument("--source-fraction", type=float, default=None,
                       metavar="Q", help=_SOURCE_FRACTION_HELP)

    pr = sub.add_parser("registry",
                        help="list codings, printers, scanners, and "
                             "profiles")
    pr.add_argument("-v", "--verbose", action="store_true",
                    help="full detail: cell/tile pitch, code + word "
                         "internals, printer print paths and notes")

    pfit = sub.add_parser(
        "fit",
        help="largest tile matrix for a paper + cell pitch, with the "
             "ready-to-use format ids")
    pfit.add_argument("--paper", default=DEFAULT_PAPER, metavar="NAME",
                      help="paper bundle: "
                           + " | ".join(sorted(PAPER_PROFILES))
                           + f" (default {DEFAULT_PAPER})")
    pfit.add_argument("--pitch", required=True, metavar="TOKEN",
                      help="cell pitch: a registered class (c1..c4) or an "
                           "exact rational NiD = N/D inch (e.g. 1i400)")
    pfit.add_argument("--dpi", type=_engine_dpi, default=DEFAULT_ENGINE_DPI,
                      metavar="N",
                      help=f"engine dot grid (default {DEFAULT_ENGINE_DPI})")

    pc = sub.add_parser(
        "capacity",
        help="plan a payload (--payload-bytes) or show the max payload "
             "for a page count (--pages)")
    add_selection(pc)
    pc.add_argument("--payload-bytes", type=int, default=None, metavar="N",
                    help="plan for a payload of N bytes: pages needed, "
                         "source/repair split")
    pc.add_argument("--pages", type=int, default=1, metavar="N",
                    help="without --payload-bytes: max payload for an "
                         "N-page volume (default 1)")
    pc.add_argument("--json", action="store_true",
                    help="machine-readable output")

    pg = sub.add_parser(
        "generate",
        help="write a printable volume: one .ps per page + a ground-truth "
             "bitmap + an optional sidecar manifest")
    add_selection(pg)
    # retained for measure/evidence_regen until the owner's ruling (CMY-GENERATOR-PLAN W2b ii)
    pg.add_argument("--coding", metavar="ID",
                    help="the evidence recipes' legacy door only "
                         "(measure/evidence_regen): a legacy coding whose "
                         "page the --printer row's margin derives, "
                         "opening onto a fossil; new work spells "
                         "--format L:<id>")
    pg.add_argument("payload", help="payload file (stored verbatim; "
                                    "length and hash ride inside the "
                                    "printed stream)")
    pg.add_argument("-o", "--out", default=None, metavar="DIR",
                    help="output directory; refused if it exists (default "
                         "build/holo-<spec>-<payload-sha12>, "
                         "content-addressed)")

    sub.add_parser(
        "decode",
        help="recover a payload from scans — forwards every argument to "
             "the holo3 receiver (`./confetti3.py decode` is the explicit "
             "spelling); see `decode --help`")

    sub.add_parser(
        "discover",
        help="emit and analyze printer/scanner characterization sheets")

    args = ap.parse_args(effective_argv)
    # `decode` and `discover` never reach here: both are intercepted above,
    # and their subparsers exist only so `--help` lists every verb.
    return {"registry": cmd_registry, "fit": cmd_fit,
            "capacity": cmd_capacity,
            "generate": cmd_generate}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
