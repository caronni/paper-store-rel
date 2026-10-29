"""The R11 stage driver: selfcheck | extract | smoke | time | run | report.

    PYTHONPATH=src:. env/bin/python -m measure.cmy_calibration --stage selfcheck
    ... --stage extract --evidence-root DIR --scale-root DIR [--captures S14-2400 S17-2400 X1-2400 S17-4800] [--ap07]
    ... --stage smoke
    ... --stage time [--budget-min 55]
    ... --stage run --evidence-root DIR [--workers 8] [--diagnostic-continue]
    ... --stage report
Artefacts go to --art (default build/cmy-calibration under the repository root); later stages read back what
earlier stages wrote there.  Inputs by flag only (2026-10-09 ruling, config's docstring): --evidence-root (or
$PAPER_EVIDENCE_ROOT) = the directory holding the published release paper-store-evidence-holo-2026-10/, its
captures unpacked to <name>.tiff by the release's tools/unpack.sh (extract, run); --scale-root = the four e041 scale
readouts, <dir>/<capture>/<tag>-{windows.csv,summary.json}, written by measure.e041_scale_readout --out <dir>/<capture>
(extract; a missing one is refused with its regeneration command).

The run of record (2026-10-10, scratch/cmy-calibration-20261010/) from the published archive (2026-10-12):
    E=<evidence root>; R=build/cmy-calibration/scale
    PYTHONPATH=src:. env/bin/python -m measure.e041_scale_readout --scan-dpi 2400 \\
        --scan $E/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S14/captures/S14-canon-2400rgb.tiff \\
        --manifest $E/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S14/jobs/S14-ps-scale.manifest.json \\
        --out $R/S14-2400
    (likewise S17-2400: S17/captures/S17-canon-2400rgb.tiff at 2400 and S17/jobs/S17-ps-layouts.manifest.json;
    S17-4800: S17-canon-4800rgb.tiff at 4800, the same manifest; X1-2400: 042-altalink-cell-encodings/X1/captures/
    X1-canon-2400rgb.tiff at 2400 and X1/jobs/X1-altalink-probe.manifest.json)
    PYTHONPATH=src:. env/bin/python -m measure.cmy_calibration --stage selfcheck
    ... --stage extract --evidence-root $E --scale-root $R
    ... --stage smoke
    ... --stage time
    ... --stage run --evidence-root $E --workers 8 --diagnostic-continue
    ... --stage report
    then measure.cmy_calibration.followup --art build/cmy-calibration (its docstring) for the follow-up arms.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from measure import _evidence
from measure.cmy_calibration import report, run
from measure.cmy_calibration.config import ARTEFACTS, CAPTURES, Params


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True, choices=("selfcheck", "extract", "smoke", "time", "run", "report"))
    ap.add_argument("--art", default=str(ARTEFACTS),
                    help="the work directory every stage writes and later stages read back (default %(default)s)")
    _evidence.add_argument(ap)
    ap.add_argument("--scale-root", type=Path, default=None,
                    help="extract: the e041 scale readouts, <dir>/<capture>/<tag>-{windows.csv,summary.json}")
    ap.add_argument("--captures", nargs="+", choices=sorted(CAPTURES), default=None,
                    help="extract only these captures (one 4800 scan at a time: they run sequentially)")
    ap.add_argument("--ap07", action="store_true", help="extract: also the 0.7-cell box column")
    ap.add_argument("--budget-min", type=float, default=55.0)
    ap.add_argument("--diagnostic-continue", action="store_true",
                    help="run: record a failed control and go on (output cmy-calibration-diagnostic.json, decisions "
                         "null, the rules' reading as decisions_unratified); off = the protocol's stop rule")
    ap.add_argument("--workers", type=int, default=None,
                    help="extract: window threads (bit-identity checked; default 1 = serial); time/run: decode threads")
    args = ap.parse_args()
    root = (_evidence.resolve(args.evidence_root, tool=f"cmy_calibration --stage {args.stage}")
            if args.stage in ("extract", "run") else None)
    if args.stage == "extract" and args.scale_root is None:
        raise SystemExit("cmy_calibration --stage extract: no scale readouts -- pass --scale-root DIR "
                         "(<dir>/<capture>/<tag>-{windows.csv,summary.json}, measure.e041_scale_readout's output)")
    art = Path(args.art)
    art.mkdir(parents=True, exist_ok=True)
    if args.stage == "selfcheck":
        out = run.stage_selfcheck(art)
        print(json.dumps(run.jsonable(out), indent=1))
        raise SystemExit(0 if out["pass"] else 1)
    if args.stage == "extract":
        out = run.stage_extract(art, tuple(args.captures) if args.captures else None, args.ap07,
                                workers=args.workers or 1, evidence_root=root, scale_root=args.scale_root)
        raise SystemExit(0 if out["pass"] else 2)
    if args.stage == "smoke":
        out = run.stage_smoke(art)
        raise SystemExit(0 if all(out[k] for k in ("C2_real", "C5", "C6")) else 1)
    if args.stage == "time":
        p = Params() if args.workers is None else replace(Params(), workers=args.workers)
        run.stage_time(art, p, args.budget_min)
        return
    if args.stage == "run":
        doc = run.stage_run(art, workers=args.workers, diagnostic_continue=args.diagnostic_continue,
                            evidence_root=root)
        raise SystemExit(0 if doc.get("decisions") is not None else 1)
    if args.stage == "report":
        diag = art / "cmy-calibration-diagnostic.json"
        name = "cmy-calibration.json" if (art / "cmy-calibration.json").exists() or not diag.exists() else diag.name
        print(report.render(art, name))


if __name__ == "__main__":
    main()
