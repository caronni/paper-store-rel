"""`python -m analyzer …` — the operator's door (PLAN §5).

    census   coverage, bands, residue, the rank cross-check
    read     the evidence stage only (no ladder)
    ladder   the full pass: evidence, combination, ladder, fixed point
    controls null arm, frame null, positive control, parity sample
    close    production ∪ analyzer certificates through close_volume
    export-facts  snapshot + ledger(s) -> a snapshot holo3 can resume
    union-base    a run dir sharing another's rasters, with new facts
    mirror   rebuild a run dir's rasters on local disk from the TIFFs
    emit-plane        one greyscale capture per RGB capture, one plane
    plane-view-decode the production K receiver, over those captures
    report   re-render the Markdown summary of an existing ledger
    score    OFFLINE: ledger(s) + a payload -> score.jsonl + score.md

Every subcommand writes into `--out` (required) and prints the numbers
it measured; nothing is hidden in a file only.

NO RUN COMMAND TAKES A PAYLOAD (RULED 2026-09-04).  `--gt-dir` and
`--payload` live on ONE door, `score`, and it is the only one that
imports `analyzer.truth`; everything above it decides blind.  The
payload `score` reads may be the emitted one or the one `close` wrote —
the envelope verified it either way.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from . import close as close_mod
from . import controls as controls_mod
from .calibrate import CTX_MODES
from . import export_facts as export_mod
from . import frame as frame_mod
from . import fixedpoint as fp
from . import inputs as inputs_mod
from . import ledger as ledger_mod
from . import mirror as mirror_mod
from . import planeview
from . import residue as residue_mod
from . import stopdoor as doors_mod
from . import unionbase as unionbase_mod
from .types import (with_profile, VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST, AnalyzerConfig, DEFAULT_ARMS,
                    DEFAULT_LADDER_RUNGS, DEFAULT_RULES, KNOWN_RUNGS,
                    PROFILES, RESERVED_KNOBS)

EXIT_WRONG = 2

#: The cap `--fixed-point` runs to convergence under, which is the
#: library's own default and not a second number kept here (R1,
#: 2026-09-06).
DEFAULT_MAX_GENERATIONS: int = AnalyzerConfig.max_generations

#: Knob names the CLI REFUSES (W8 B1, APPROACHES §4.0 ruling 8): each is
#: derived inside `blind_key` and assigned there unconditionally, so a
#: value from the command line would be a lie about where it came from.
#: ONE tuple, `types.RESERVED_KNOBS`, re-exported here (the review of
#: 2026-09-06: two copies is two ways for the parse-time refusal and
#: `blind_key`'s own to drift apart).
__all_reserved__ = RESERVED_KNOBS


class KnobError(ValueError):
    """A `--knob` the CLI will not pass on."""


def _list(value: str | None, fallback: Sequence[str]) -> tuple[str, ...]:
    if not value:
        return tuple(fallback)
    return tuple(name.strip() for name in value.split(",") if name.strip())


def parse_knob(item: str) -> tuple[str, Any]:
    """``KEY=VALUE`` -> ``(key, value)``; VALUE is JSON when it parses.

    `branches=state` is the string `"state"`, `ctx_state=true` is `True`,
    `patch_shrinkage=0.01` is a float, `L2=[{"mode": ...}]` is a list.  A
    reserved name is refused with a message, never silently dropped.
    """
    name, separator, raw = str(item).partition("=")
    name = name.strip()
    if not separator or not name:
        raise KnobError(f"--knob wants KEY=VALUE, got {item!r}")
    if name in RESERVED_KNOBS:
        raise KnobError(
            f"knob {name!r} is reserved: it is derived inside blind_key and "
            f"assigned there (reserved: {', '.join(RESERVED_KNOBS)})")
    try:
        value: Any = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    return name, value


def parse_knobs(items: Sequence[str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items or ():
        name, value = parse_knob(item)
        out[name] = value
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyzer", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(name: str, help_text: str) -> argparse.ArgumentParser:
        item = sub.add_parser(name, help=help_text)
        item.add_argument("--run-dir", required=True, type=Path)
        item.add_argument("--out", required=True, type=Path,
                          help="artefact directory")
        item.add_argument(
            "--format-ref", dest="format_ref", default=None,
            help="replace the format id the run's RunOpen declares (a "
                 "format id IS the AES seed; sheet J needs "
                 "L:c2-cmy8-r0547@53x37 — PLAN §6)")
        item.add_argument("--seed", type=int, default=20260903)
        item.add_argument("--workers", type=int, default=4)
        item.add_argument("--cover-fraction", type=float, default=0.9)
        item.add_argument("--profile", default=None,
                          help="a named measured configuration from "
                               "types.PROFILES (e.g. everything, patch, "
                               "everything+patch, pure); it supplies what "
                               "the operator did not say — an explicit "
                               "--arms/--rules/--rungs/--halo-cells/"
                               "--ctx-mode/--no-reroll/--reroll-only-arms "
                               "WINS over it (W8 B5)")
        item.add_argument("--halo-cells", default=None,
                          metavar="WIDTH|C=..,M=..,Y=..",
                          help="override the per-stream halo (production "
                               "is 16 C, 16 M, 32 Y).  A bare width sets "
                               "all three; the per-plane spelling "
                               "C=48,M=48,Y=32 names them and must name "
                               "every one (2026-09-07: `--halo-cells 48` "
                               "is 48/48/48, which is NOT the wide-halo "
                               "profile's 48/48/32)")
        item.add_argument("--ctx-mode", dest="ctx_mode", default=None,
                          choices=CTX_MODES,
                          help="the calibration's context stage "
                               "(default production); `none` is the control, "
                               "`local5` the 5x5-neighbourhood fit for "
                               "label-starved bands")
        item.add_argument("--no-reroll", dest="no_reroll",
                          action="store_true",
                          help="turn the re-roll across the unselected arms "
                               "OFF (it is ON by default and minted ~240 of "
                               "sheet H's 508 certificates)")
        item.add_argument(
            "--reroll-only-arms", dest="reroll_only_arms", default=None,
            metavar="ARM[,ARM]",
            help="PLACE these arms in the re-roll only (W8 B8): they are "
                 "computed for a key the battery could NOT close and never "
                 "for one it did, and they can never win the select fold.  "
                 "The one-pass door to what the `patch-then-pure` and "
                 "`everything+patch+pure` profiles name; the ledger header "
                 "records it and a certificate says reroll:<arm>")
        item.add_argument("--pages", type=str, default=None)
        return item

    def knob_door(item: argparse.ArgumentParser) -> None:
        item.add_argument(
            "--knob", action="append", default=None, metavar="KEY=VALUE",
            help="a library knob (JSON value, else a string), repeatable; "
                 "merged AFTER --profile so the operator's value wins; "
                 f"reserved: {', '.join(RESERVED_KNOBS)}")

    census = common("census", "coverage, bands, residue, rank cross-check")
    census.add_argument("--check-rank", action="store_true", default=True)
    census.add_argument("--no-check-rank", dest="check_rank",
                        action="store_false")

    for name, help_text in (("read", "the evidence stage only"),
                            ("ladder", "the full pass")):
        item = common(name, help_text)
        item.add_argument("--targets", default="residue",
                          help="residue | band:dead | band:marginal | "
                               "stream:C | list FILE | "
                               "'open-after LEDGER[,LEDGER]'")
        item.add_argument("--arms", default=None)
        item.add_argument("--rules", default=None)
        item.add_argument("--rungs", default=None)
        item.add_argument(
            "--fixed-point", action="store_true",
            help="run the cascade to convergence under the default cap "
                 f"({DEFAULT_MAX_GENERATIONS}); with --max-generations "
                 "that cap bounds the convergence")
        item.add_argument(
            "--max-generations", type=int, default=None, metavar="N",
            help="run up to N generations, stopping early the moment a "
                 "generation re-attacks nothing; usable on its own "
                 "(neither flag = ONE generation)")
        item.add_argument("--limit", type=int, default=None,
                          help="stop after this many targets (a smoke run)")
        item.add_argument("--progress-every", type=int,
                          default=fp.PROGRESS_EVERY,
                          help="a progress tick on stderr every N finished "
                               "keys (0 = generation lines only); SIGUSR1 "
                               "or ctrl-T prints a status line any time")
        item.add_argument(
            "--checkpoint-minutes", dest="checkpoint_minutes", type=float,
            default=fp.CHECKPOINT_MINUTES, metavar="M",
            help=f"write {fp.CHECKPOINT_NAME} beside the ledger every M "
                 f"minutes (0 disables); it carries the generation, the "
                 f"key counts, the exposure, the knobs and the peak RSS, "
                 f"and it names the recovery recipe — there is no "
                 f"--resume")
        item.add_argument("--no-maps", action="store_true")
        knob_door(item)

    control = common("controls", "the controls of DESIGN §8")
    knob_door(control)
    control.add_argument("--parity", type=int, default=100)
    control.add_argument("--null", type=int, default=5)
    control.add_argument("--frame-null", type=int, default=3)
    control.add_argument("--withhold-run-mints", action="store_true")
    control.add_argument("--withhold-keys", type=Path, default=None)
    control.add_argument("--withhold-source", default=None)
    control.add_argument(
        "--holdout-stratified", default=None, metavar="SPEC",
        help="Q1.7: withhold production certificates by (stream, source), "
             "e.g. 'Y:tiles/planek150=60,C:tiles/local150=20'; one pass, "
             "no cascade, recovered fraction per (stream, source, band)")
    control.add_argument("--arms", default=None)
    control.add_argument("--rules", default=None)
    control.add_argument("--rungs", default=None)
    control.add_argument(
        "--targets", default=None, metavar="SPEC",
        help="W8 B3: restrict the census population the controls draw "
             "from, in `read`/`ladder`'s own target grammar ('list FILE', "
             "'band:dead', 'stream:C', 'open-after LEDGER').  NOTE that "
             "every control draws its donors from PRODUCTION CERTIFICATES "
             "(`null_arm` and `frame_null` shift a certified tile's "
             "pixels or frame; `parity_sample` re-derives certificates), "
             "so a residue spec — or a list of open rows — leaves them "
             "nothing to draw and they refuse.  Name certified rows of "
             "the regime you want controlled.")

    closer = common("close", "close_volume on the union")
    closer.add_argument("--ledger", type=Path, default=None)
    closer.add_argument(
        "--no-consistency", action="store_true",
        help="skip the fountain consistency check (one extra solve plus "
             "one re-encode of every certified symbol)")
    closer.add_argument(
        "--localize", action="store_true",
        help="when the fountain is inconsistent, name the poisoned "
             "symbol(s), exclude them and close on the survivors")

    mirror = sub.add_parser(
        "mirror", help="rebuild a run dir's rasters on local disk")
    mirror.add_argument("--src-run-dir", dest="src_run_dir", required=True,
                        type=Path,
                        help="the finished run dir whose rasters are "
                             "unreachable or slow (a network mount)")
    mirror.add_argument("--out", required=True, type=Path,
                        help="the local run dir to build")
    mirror.add_argument("--tiff-dir", dest="tiff_dir", type=Path,
                        default=None,
                        help="look the argv basenames up in this directory "
                             "instead of where argv says")
    mirror.add_argument(
        "--format-ref", dest="format_ref", default=None,
        help="replace the format id the run's RunOpen declares "
             "(pitch and family drive the level ladder)")

    emit_plane = sub.add_parser(
        "emit-plane",
        help="one greyscale capture per RGB capture, holding one plane")
    emit_plane.add_argument("--run-dir", required=True, type=Path,
                            help="a local run dir with rasters "
                                 "(analyzer mirror builds one)")
    emit_plane.add_argument("--plane", default="C", choices=("C", "M", "Y"),
                            help="which cmy8 stream to unmix (default C)")
    emit_plane.add_argument("--out", required=True, type=Path,
                            help="directory for the TIFFs and sidecars")
    emit_plane.add_argument("--lanes", default=inputs_mod.LANES_FINEST_COVERING,
                            choices=inputs_mod.LANE_POLICIES,
                            help="lane policy for the run's certificates")
    emit_plane.add_argument("--unmix", default="lane",
                            choices=planeview.emit.UNMIX_SCOPES,
                            help="mixing-fit scope: lane (12 sampled tiles) "
                                 "or page (96)")
    emit_plane.add_argument("--page", type=int, default=0,
                            help="which printed page to fit the mix on")
    emit_plane.add_argument(
        "--format-ref", dest="format_ref", default=None,
        help="replace the format id the run's RunOpen declares")

    plane_decode = sub.add_parser(
        "plane-view-decode",
        help="run the production K receiver over emitted plane captures")
    plane_decode.add_argument("scans", nargs="+", type=Path,
                              help="the -plane-<S>.tiff captures")
    plane_decode.add_argument("--dpi", action="append", type=float,
                              default=[], required=True,
                              help="one per scan, in order")
    plane_decode.add_argument("--format", dest="format_ref", required=True,
                              help="the SOURCE cmy8 format id, e.g. "
                                   "L:c2-cmy8-r0850-p120-x1@3392x2368")
    plane_decode.add_argument("--plane", default="C",
                              choices=("C", "M", "Y"),
                              help="which stream the captures hold")
    plane_decode.add_argument("--out", required=True, type=Path,
                              help="holo3 --out (never written: --no-close)")
    plane_decode.add_argument("--run-dir", dest="run_dir", required=True,
                              type=Path, help="holo3 --run-dir base")
    plane_decode.add_argument("--workers", type=int, default=1)
    plane_decode.add_argument("--diag", type=int, default=None,
                              metavar="PORT")
    plane_decode.add_argument("--manifest", type=Path, default=None,
                              help="write the row/seam/argv record here")
    plane_decode.add_argument("--dry-run", action="store_true",
                              help="build the row and the command line, "
                                   "verify the seams, run nothing")
    plane_decode.add_argument("--holo3-option", dest="extra", default=[],
                              action="append", metavar="TOKEN",
                              help="extra holo3 decode token, repeatable")

    export = sub.add_parser(
        "export-facts",
        help="snapshot + ledger(s) -> a new snapshot holo3 can resume")
    export.add_argument("--snapshot", required=True, type=Path,
                        help="the base run's facts.npz (never overwritten)")
    export.add_argument("--ledger", required=True, type=Path,
                        action="append", dest="ledgers",
                        help="analyzer ledger.jsonl; repeatable, first wins")
    export.add_argument("--out", required=True, type=Path,
                        help="the new snapshot; its manifest is written "
                             "beside it as <out>.manifest.json")
    export.add_argument(
        "--format-ref", dest="format_ref", default=None,
        help="override the format ref the ledger headers declare (the "
             "consistency check resolves it; sheet J needs "
             "L:c2-cmy8-r0547@53x37)")
    export.add_argument("--include-list-rungs", dest="include_list_rungs",
                        action="store_true", default=True,
                        help="fold certified_list rows too (the default; "
                             "they are counted separately)")
    export.add_argument("--no-list-rungs", dest="include_list_rungs",
                        action="store_false")
    export.add_argument("--dry-run", action="store_true",
                        help="print the manifest and write nothing")

    union = sub.add_parser(
        "union-base",
        help="a run dir sharing another's rasters, with new facts")
    union.add_argument("--run-dir", required=True, type=Path,
                       help="the base run dir whose rasters, report, "
                            "events and argv are borrowed")
    union.add_argument("--facts", required=True, type=Path,
                       help="the facts.npz the new dir uses (an "
                            "`export-facts` output); SYMLINKED, not copied")
    union.add_argument("--out", required=True, type=Path,
                       help="the new run dir to build")
    union.add_argument("--no-verify-facts", dest="verify_facts",
                       action="store_false", default=True,
                       help="skip reading the snapshot to check its capture "
                            "ids against the base run's (it costs 6-12 GB "
                            "of RSS; the check is what keeps a pose from "
                            "being applied to another capture's pixels)")

    scorer = sub.add_parser(
        "score", help="OFFLINE: ledger(s) + a payload -> score.jsonl/.md")
    scorer.add_argument("--ledger", required=True, type=Path,
                        action="append", dest="ledgers",
                        help="analyzer ledger.jsonl; repeatable")
    scorer.add_argument("--payload", required=True, type=Path,
                        help="the payload to score against: the emitted "
                             "one, or the payload.bin a close wrote")
    scorer.add_argument("--gt-dir", type=Path,
                        help="generation dir; sha-gates the payload against "
                             "its manifest and supplies the emitted cell "
                             "field for the cell-level splits")
    scorer.add_argument("--run-dir", type=Path,
                        help="the run dir; enables the detector columns "
                             "(cell error, d', AUC, R, the waterfall) by "
                             "recomputing the default arm's evidence")
    scorer.add_argument("--out", required=True, type=Path)
    scorer.add_argument("--format-ref", dest="format_ref", default=None,
                        help="override the format ref the ledger headers "
                             "declare")
    scorer.add_argument("--seed", type=int, default=20260903)
    scorer.add_argument("--workers", type=int, default=4)
    scorer.add_argument("--cover-fraction", type=float, default=0.9)
    scorer.add_argument("--halo-cells", default=None,
                        metavar="WIDTH|C=..,M=..,Y=..")
    scorer.add_argument("--arms", default=None,
                        help="the FIRST arm is the one whose evidence is "
                             "recomputed and scored")
    scorer.add_argument("--limit", type=int, default=None,
                        help="score the evidence of at most this many rows "
                             "(certificates and rungs are always all)")
    scorer.add_argument("--pages", type=int, default=None,
                        help="printed pages the GT reconstruction covers; "
                             "taken from --run-dir when given, else 1 "
                             "(sheet J needs 2)")
    scorer.add_argument("--maps", action="store_true",
                        help="write the bits-wrong PNG per plane")
    knob_door(scorer)

    report = sub.add_parser("report", help="re-render a ledger's summary")
    report.add_argument("ledger", type=Path)
    report.add_argument("--out", type=Path, default=None)
    report.add_argument(
        "--format-ref", dest="format_ref", default=None,
        help="accepted for symmetry; a ledger carries its own header")
    return parser


# ------------------------------------------------------------- plumbing

def _out_dir(args: Any) -> Path:
    path = Path(args.out)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load(args: Any) -> Any:
    """The run dir, and nothing else (RULED 2026-09-04).

    This function used to load ground truth beside it whenever
    `--gt-dir/--payload` were given, which is how truth reached every
    command in the file.  Both flags are gone from every run command;
    scoring is `analyzer score`, offline.
    """
    return inputs_mod.load_run(
        args.run_dir, format_ref=getattr(args, "format_ref", None))


#: The flags a profile may NOT overrule (W8 B5, APPROACHES §4.0 ruling 5).
#: Each maps the `args` attribute the operator sets to the
#: `AnalyzerConfig` field it lands in; a profile supplies only what the
#: operator did not say.
EXPLICIT_OVER_PROFILE: tuple[tuple[str, str], ...] = (
    ("arms", "arms"), ("rules", "rules"), ("rungs", "rungs"),
    ("halo_cells", "halo_cells"), ("ctx_mode", "ctx_mode"),
    ("no_reroll", "reroll"), ("reroll_only_arms", "reroll_only_arms"))


class NameRefused(ValueError):
    """An arm, rule or rung name the CLI will not pass on (W8 B5)."""


def _validate_names(config: AnalyzerConfig) -> None:
    """Refuse a misspelled arm, rule or rung BEFORE the run dir is opened.

    Every one of these names is checked deep inside a pass today — an arm
    at the first `evidence_for`, a rung inside a worker at the first key,
    a rule at the first `combine` — so a typo in a fourteen-worker union
    pass surfaced as a per-row refusal, or as hours of work that produced
    nothing.  The names are cheap to check and the check costs one import
    the CLI already carries.  Nothing here is a policy: the sets are the
    dispatch tables themselves (`arms.parse_arm`, `combine.RULES`,
    `types.KNOWN_RUNGS`).
    """
    from .arms import ArmError, parse_arm
    from .combine import RULES
    for field in ("arms", "reroll_only_arms"):
        for arm in getattr(config, field, ()) or ():
            try:
                parse_arm(str(arm))
            except (ArmError, ValueError) as error:
                raise NameRefused(
                    f"--{field.replace('_', '-')}: {error}") from error
    for rule in config.rules:
        if str(rule) not in RULES:
            raise NameRefused(
                f"--rules: unknown rule {rule!r} "
                f"(known: {', '.join(RULES)})")
    for rung in config.rungs:
        if str(rung) not in KNOWN_RUNGS:
            raise NameRefused(
                f"--rungs: unknown rung {rung!r} "
                f"(known: {', '.join(KNOWN_RUNGS)})")


def _generation_cap(args: Any) -> int:
    """The generation cap the two flags ask for (ruling R1, 2026-09-06).

    They are ORTHOGONAL.  `--max-generations N` alone runs up to N
    generations — the driver stops early the moment a generation
    re-attacks nothing, so the cap is a bound and never a demand for N
    generations of work.  `--fixed-point` alone runs to convergence
    under the library's default cap.  Together, the cap bounds the
    convergence.  With neither the pass runs ONE generation, which is
    what every pass in the record did.

    What this replaces: `--max-generations N` used to be silently
    DISCARDED unless `--fixed-point` came with it (the W8 smoke's
    `--max-generations 2` passes were single generations and nobody was
    told; APPROACHES §6.5).  A cap the operator spelled is now the cap,
    and a cap below one is refused rather than run as zero generations.
    """
    said = getattr(args, "max_generations", None)
    if said is None:
        return (DEFAULT_MAX_GENERATIONS
                if getattr(args, "fixed_point", False) else 1)
    cap = int(said)
    if cap < 1:
        print(f"GENERATIONS REFUSED: --max-generations must be >= 1 "
              f"(got {cap})", file=sys.stderr)
        raise SystemExit(EXIT_WRONG)
    return cap


def _config(args: Any, **overrides: Any) -> AnalyzerConfig:
    halo = None
    if getattr(args, "halo_cells", None) is not None:
        # the PER-PLANE spelling (HALO-CHANNEL §4.5): `48` is all three,
        # `C=48,M=48,Y=32` names them, and a typo is refused here rather
        # than at the first key of a fourteen-worker pass
        try:
            halo = frame_mod.parse_halo_cells(args.halo_cells)
        except frame_mod.HaloError as error:
            print(f"HALO REFUSED: {error}", file=sys.stderr)
            raise SystemExit(EXIT_WRONG) from error
    base = dict(
        arms=_list(getattr(args, "arms", None), DEFAULT_ARMS),
        rules=_list(getattr(args, "rules", None), DEFAULT_RULES),
        rungs=_list(getattr(args, "rungs", None), DEFAULT_LADDER_RUNGS),
        workers=int(args.workers), seed=int(args.seed),
        halo_cells=halo, halo_from="cli" if halo else "defaults",
        cover_fraction=float(args.cover_fraction),
        max_generations=_generation_cap(args),
        targets_from=str(getattr(args, "targets", "explicit")),
        knobs_from="cli",
    )
    if getattr(args, "ctx_mode", None) is not None:
        base["ctx_mode"] = str(args.ctx_mode)
    if getattr(args, "no_reroll", False):
        base["reroll"] = False
    if getattr(args, "reroll_only_arms", None) is not None:
        base["reroll_only_arms"] = _list(args.reroll_only_arms, ())
    base.update(overrides)
    config = AnalyzerConfig(**base)
    from dataclasses import replace as dc_replace
    profile = getattr(args, "profile", None)
    said_it = False
    if profile:
        config = with_profile(config, str(profile))
        # PRECEDENCE (W8 B5): the profile is a default set, not an order.
        # Anything the operator spelled explicitly is re-applied over it,
        # so `--profile patch --arms "patch+offset"` isolates one arm
        # inside the profile's knobs instead of silently running three.
        explicit = {field: base[field]
                    for flag, field in EXPLICIT_OVER_PROFILE
                    if field in base and _said(args, flag)
                    and field not in overrides}
        if "halo_cells" in PROFILES.get(str(profile), {}):
            config = dc_replace(config, halo_from=f"profile:{profile}")
        if explicit:
            if "halo_cells" in explicit:
                explicit["halo_from"] = "cli"
            config = dc_replace(config, **explicit)
            #: THE HALO IS NOT A KNOB (HALO-CHANNEL-2026-09-07 §4.5).  A
            #: run whose only CLI word was `--halo-cells` used to read
            #: `knobs_from: profile:patch+cli`, and a reader diffing that
            #: one field would call it a knob-pinned run.  `halo_from`
            #: carries the halo's provenance now, and `knobs_from` is
            #: left to the knobs.
            said_it = bool(set(explicit) - {"halo_cells", "halo_from"})
    # `--knob` lands AFTER the profile (W8 B1): the operator's value wins,
    # and the header says both had a hand in it.
    try:
        given = parse_knobs(getattr(args, "knob", None))
    except KnobError as error:
        print(f"KNOB REFUSED: {error}", file=sys.stderr)
        raise SystemExit(EXIT_WRONG) from error
    if given:
        config = dc_replace(config, knobs={**dict(config.knobs), **given})
        said_it = True
    if said_it:
        config = dc_replace(
            config, knobs_from=(f"{config.knobs_from}+cli" if profile
                                else "cli"))
    # a malformed patch_* / pure_* knob is refused HERE, before a run dir is
    # loaded, not at the first key of a fourteen-worker pass
    from . import patch as patch_mod
    from . import pure as pure_mod
    try:
        patch_mod.spec_from_knobs(config.knobs)
        pure_mod.spec_from_knobs(config.knobs)
    except (patch_mod.PatchError, pure_mod.PureError) as error:
        print(f"KNOB REFUSED: {error}", file=sys.stderr)
        raise SystemExit(EXIT_WRONG) from error
    # and so is a misspelled arm, rule or rung (W8 B5)
    try:
        _validate_names(config)
    except NameRefused as error:
        print(f"NAME REFUSED: {error}", file=sys.stderr)
        raise SystemExit(EXIT_WRONG) from error
    return config


def _said(args: Any, flag: str) -> bool:
    """Did the operator spell this flag, as opposed to leaving it out?

    `--no-reroll` is a `store_true`, so "said" means True; every other
    flag in `EXPLICIT_OVER_PROFILE` defaults to None.
    """
    value = getattr(args, flag, None)
    return bool(value) if flag == "no_reroll" else value is not None


def _census(run: Any, args: Any) -> list:
    pages = None
    if getattr(args, "pages", None):
        pages = [int(value) for value in args.pages.split(",")]
    return residue_mod.census(run, pages=pages,
                              events=inputs_mod.read_tile_outcomes(
                                  Path(args.run_dir)),
                              check_rank=bool(getattr(args, "check_rank",
                                                      False)))


def _targets(rows: Sequence[Any], spec: str) -> list:
    if unionbase_mod.is_open_after(spec):
        return unionbase_mod.open_after(rows, spec)
    if spec.startswith("list "):
        wanted = set()
        for line in Path(spec.split(" ", 1)[1]).read_text(
                "utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                page, ty, tx, stream = line.split(",")
                wanted.add((int(page), int(ty), int(tx), stream.strip()))
        return [row for row in rows if row.key in wanted]
    return residue_mod.target_rows(rows, spec)


# ------------------------------------------------------------- commands

def cmd_census(args: Any) -> int:
    run = _load(args)
    rows = _census(run, args)
    out = _out_dir(args)
    ledger_mod.write_rows(out / "census.jsonl", rows,
                          {"command": "census", "run_dir": str(args.run_dir),
                           "format_ref": run.format_ref,
                           "seed": int(args.seed)})
    residue = residue_mod.residue_rows(rows)
    ranks = residue_mod.rank_check(run)
    print(f"rows {len(rows)}  covered "
          f"{sum(1 for row in rows if row.covered)}  "
          f"certified {sum(1 for row in rows if row.certified_by_production)} "
          f" residue {len(residue)}")
    for row in residue:
        print(f"  residue {row.key} band={row.band} band_any={row.band_any} "
              f"neighbours={row.neighbours_certified} "
              f"siblings={row.siblings_certified} "
              f"labels={row.n_discriminating_labels}")
    print("rank:", json.dumps(ledger_mod.jsonable(ranks)))
    (out / "census-rank.json").write_text(
        json.dumps(ledger_mod.jsonable(ranks), indent=2), "utf-8")
    return 0


def _operator_line(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def _pass(args: Any, *, rungs: Sequence[str] | None = None) -> int:
    run = _load(args)
    rows = _census(run, args)
    targets = _targets(rows, args.targets)
    if args.limit is not None:
        targets = targets[:int(args.limit)]
    overrides: dict[str, Any] = {}
    if rungs is not None:
        overrides["rungs"] = tuple(rungs)
        overrides["rules"] = ("sum",)
    config = _config(args, **overrides)
    print(f"targets {len(targets)}  arms {len(config.arms)}  "
          f"rules {config.rules}  rungs {config.rungs}  "
          f"workers {config.workers}  "
          # R1: the cap the pass actually runs under, said out loud — a
          # discarded `--max-generations` was invisible until the ledger.
          f"generations <={config.max_generations}")
    every = int(getattr(args, "progress_every", fp.PROGRESS_EVERY))
    # THE OUT DIR AND THE LEDGER BEFORE THE FIRST KEY (2026-09-13).  Both
    # used to be made after `fp.run` returned, so the pass killed on
    # 09-10 at 350 keys and 51 certificates left NOTHING behind — and the
    # rows it was holding to write them were the process's largest
    # object.  Now the header goes down first, each row as its generation
    # folds it, each certificate as it lands (`mints.jsonl`), and a
    # checkpoint at the first key boundary after each half hour.
    out = _out_dir(args)
    name = "ledger" if rungs is None else "ledger-read"
    ledger_path = out / f"{name}.jsonl"
    writer = ledger_mod.LedgerWriter(ledger_path)
    minutes = float(getattr(args, "checkpoint_minutes",
                            fp.CHECKPOINT_MINUTES))
    checkpoint = fp.Checkpointer(out / fp.CHECKPOINT_NAME, minutes=minutes,
                                 emit=_operator_line)
    _operator_line(
        f"ledger {ledger_path} (streamed), mints {writer.mints_path}, "
        f"checkpoint {'off' if minutes <= 0 else f'every {minutes:g} min'}"
        + ("" if not writer.kept_aside else
           "; kept aside " + ", ".join(str(moved)
                                       for moved in writer.kept_aside))
        + f"; {doors_mod.RECOVERY_RECIPE}")

    try:
        result = fp.run(run, targets, config, census_rows=rows,
                        progress=_operator_line,
                        progress_every=every if every > 0 else len(targets) + 1,
                        writer=writer, checkpoint=checkpoint,
                        fixed_point=bool(getattr(args, "fixed_point", False)))
    except BaseException:
        writer.close()          # what it has written stays readable
        raise
    writer.finish(result.header)
    close_row = None
    if rungs is None:
        certs = dict(result.certified)
        if result.header.get("stop_reason") == fp.STOP_INTERRUPTED:
            # The stop door's products (2026-09-07): a pass the operator
            # stopped owes the same close an exhausted one writes, and
            # the exported snapshot their next holo3 `--resume` reads —
            # each guarded, each printing its own outcome.
            close_row = doors_mod.interrupt_products(
                run, certs, out, ledger_path=ledger_path,
                emit=_operator_line)
        else:
            close_row = close_mod.close(run, certs, out_dir=out)
            (out / "close.json").write_text(
                json.dumps(ledger_mod.jsonable(close_row), indent=2), "utf-8")
        result.close_row = close_row
        # The pass's blind cross-check, beside its ledger (PAGE-FIELD-PLAN
        # A2): the pooled `field2` fields the run's own arms fitted, in
        # the schema `measure/page_field/compare.py --analyzer` reads,
        # each carrying the revision of the production field that STOOD
        # for that (page, plane).  So `--fields <production> --analyzer
        # field2.json` is the consistency check of what THIS pass read;
        # the standalone measurement is phase C's.
        #
        # GUARDED, in the stop door's spelling: this is a product, never
        # the pass.  It is written mid-sequence, before `ledger.md`, the
        # maps and the summary, and a raise here would cost a multi-hour
        # ladder all three over a diagnostic.
        try:
            product = fp.write_field2_product(
                run, config, out / fp.FIELD2_PRODUCT_NAME,
                pass_token=result.header.get("pass_token"))
            print(f"field2: {len(product['fields'])} pooled field(s) in "
                  f"{out / fp.FIELD2_PRODUCT_NAME}")
        except Exception as error:          # a product, never the pass
            _operator_line(f"field2: the product FAILED "
                           f"({type(error).__name__}: {error})")
    # The report reads the LEDGER, not the pass: `result.rows` is empty
    # on a streamed pass, and the file is the one artefact that carries
    # every row — the last one per key, the superseded attempts counted
    # and skipped, a half-written line tolerated and counted.
    stats = ledger_mod.ReadStats()
    summary = ledger_mod.summarize(
        ledger_mod.iter_rows_latest(ledger_path, stats=stats),
        header=result.header, close_row=close_row)
    (out / f"{name}.md").write_text(summary, "utf-8")
    print(f"ledger {ledger_path}: {stats.rows} row(s) read, "
          f"{stats.superseded} superseded, {writer.n_mints} mint(s) in "
          f"{writer.mints_path}"
          + (f", {stats.truncated_lines} TRUNCATED line(s)"
             if stats.truncated_lines else ""))
    if rungs is None and not args.no_maps:
        written = ledger_mod.render_maps(
            ledger_mod.iter_rows_latest(ledger_path), out,
            tiles_yx=run.tiles_yx, live_pages=run.live_pages)
        print(f"maps: {len(written)} PNG(s) in {out}")
    print(summary)
    return 0


def cmd_read(args: Any) -> int:
    return _pass(args, rungs=())


def cmd_ladder(args: Any) -> int:
    return _pass(args)


def cmd_controls(args: Any) -> int:
    run = _load(args)
    rows = _census(run, args)
    if getattr(args, "targets", None):
        rows = _targets(rows, str(args.targets))
    config = _config(args)
    out = _out_dir(args)
    report: dict[str, Any] = {}

    certified = [row for row in rows if row.certified_by_production]
    if args.parity:
        report["parity"] = controls_mod.parity_sample(
            run, rows, config, n_per_stream=int(args.parity))
    if args.null:
        keys = [row.key for row in controls_mod.stratified_sample(
            certified, max(1, int(args.null) // 3), config.seed)]
        report["null_arm"] = controls_mod.null_arm(run, keys, config)
    if args.frame_null:
        keys = [row.key for row in controls_mod.stratified_sample(
            certified, max(1, int(args.frame_null) // 3), config.seed)]
        report["frame_null"] = controls_mod.frame_null(run, keys, config)
    if getattr(args, "holdout_stratified", None):
        report["stratified_holdout"] = controls_mod.stratified_holdout(
            run, rows, args.holdout_stratified, config)
    if args.withhold_run_mints or args.withhold_keys or args.withhold_source:
        withheld = controls_mod.withheld_keys(
            run, run_mints=bool(args.withhold_run_mints),
            keys_file=args.withhold_keys,
            sources=_list(args.withhold_source, ()))
        report["positive_control"] = controls_mod.positive_control(
            run, withheld, config, census_rows=rows)
    (out / "controls.json").write_text(
        json.dumps(ledger_mod.jsonable(report), indent=2, sort_keys=True),
        "utf-8")
    print(json.dumps(ledger_mod.jsonable(report), indent=2, sort_keys=True))
    failures = [name for name, body in report.items()
                if isinstance(body, dict) and body.get("passes") is False]
    if failures:
        print(f"CONTROLS FAILED: {failures}", file=sys.stderr)
        return 1
    return 0


def cmd_close(args: Any) -> int:
    run = _load(args)
    out = _out_dir(args)
    certs: dict = {}
    if args.ledger is not None:
        # STREAMED and last-write-wins: a ledger is gigabytes, and a key
        # a later generation re-attacked carries more than one row.
        for row in ledger_mod.iter_rows_latest(args.ledger):
            bits = (row.get("rungs") or {}).get("user_bits")
            if bits is not None and row.get("verdict") in (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST):
                certs[(int(row["page"]), int(row["ty"]), int(row["tx"]),
                       str(row["stream_id"]))] = np.asarray(bits, np.uint8)
    result = close_mod.close(
        run, certs, out_dir=out,
        check_consistency=not bool(getattr(args, "no_consistency", False)),
        localize_poison=bool(getattr(args, "localize", False)))
    # The corrected bits are numpy vectors for a library caller; the JSON
    # keeps the sha and the flip count that `localize` already summarised.
    printable = {name: value for name, value in result.items()}
    if "localize" in printable:
        printable["localize"] = {
            name: value for name, value in printable["localize"].items()
            if name != "corrected_user_bits"}
    (out / "close.json").write_text(
        json.dumps(ledger_mod.jsonable(printable), indent=2), "utf-8")
    print(json.dumps(ledger_mod.jsonable(printable), indent=2))
    # Exit 0 ONLY on a VERIFIED close.  The verification is the payload
    # envelope's own sha (RULED 2026-09-04) — `close_volume` checks the
    # digest the emitter wrote inside the volume — and the recovered
    # bytes are in `<out>/payload.bin`, which is what `analyzer score`
    # can then be pointed at.
    if not result["verified"]:
        print(f"CLOSE NOT VERIFIED: status={result['status']} "
              f"reason={result.get('unverified_reason')}", file=sys.stderr)
        return EXIT_WRONG
    return 0


def cmd_mirror(args: Any) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        result = mirror_mod.mirror(args.src_run_dir, out,
                                   format_ref=args.format_ref,
                                   tiff_dir=args.tiff_dir)
    except mirror_mod.MirrorError as error:
        print(f"MIRROR REFUSED: {error}", file=sys.stderr)
        return 1
    (out / "mirror.json").write_text(
        json.dumps(ledger_mod.jsonable(result), indent=2), "utf-8")
    print(json.dumps(ledger_mod.jsonable(result), indent=2))
    return 0


def cmd_export_facts(args: Any) -> int:
    try:
        manifest = export_mod.export(
            args.snapshot, args.ledgers, args.out,
            format_ref=args.format_ref,
            include_list_rungs=bool(args.include_list_rungs),
            dry_run=bool(args.dry_run))
    except export_mod.ExportError as error:
        print(f"EXPORT REFUSED: {error}", file=sys.stderr)
        return EXIT_WRONG
    print(json.dumps(ledger_mod.jsonable(manifest), indent=2))
    counts = manifest["counts"]
    print(f"{'DRY RUN — nothing written' if args.dry_run else args.out}: "
          f"{counts['snapshot_certificates']} + {counts['added']} = "
          f"{counts['total_after_export']} certificates "
          f"({counts['skipped_already_certified']} already certified, "
          f"{counts['added_certified_list']} from list rungs)")
    return 0


def cmd_emit_plane(args: Any) -> int:
    run = inputs_mod.load_run(args.run_dir, lanes=args.lanes,
                              format_ref=args.format_ref)
    try:
        emissions = planeview.emit_run(
            run, args.out, stream_id=args.plane, page=int(args.page),
            unmix_scope=args.unmix)
    except planeview.EmitError as error:
        print(f"EMIT REFUSED: {error}", file=sys.stderr)
        return 1
    manifest = [item.as_json() for item in emissions]
    out = Path(args.out)
    (out / f"emit-plane-{args.plane}.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), "utf-8")
    for item in emissions:
        print(f"{item.basename}: {item.out_path} "
              f"{item.shape_yx[0]}x{item.shape_yx[1]} @ {item.dpi} dpi  "
              f"w=({item.functional_w[0]:+.4f}, {item.functional_w[1]:+.4f}, "
              f"{item.functional_w[2]:+.4f})  "
              f"anchors paper {item.paper_anchor:+.4f} / ink "
              f"{item.ink_anchor:+.4f} "
              f"({item.n_paper_labels}/{item.n_ink_labels} labels)  "
              f"span {item.span_bright_score:+.3f}..."
              f"{item.span_dark_score:+.3f} over {item.span_pixels} px "
              f"-> paper u8 {item.paper_level_u8:.0f} / ink "
              f"{item.ink_level_u8:.0f}  "
              f"clipped {item.clipped_low_fraction:.2e} low (signal) / "
              f"{item.clipped_high_fraction:.2e} high (platen)  "
              f"levels p1/p50/p99 "
              f"{'/'.join(str(v) for v in item.level_percentiles_u8)}  "
              f"{item.fraction_inside_span:.3f} inside the span  "
              f"sha {item.out_sha256[:12]}")
    print(f"{len(emissions)} capture(s) -> {out}")
    return 0


def cmd_plane_view_decode(args: Any) -> int:
    try:
        decode_plan = planeview.plan(
            args.format_ref, args.plane, args.scans, args.dpi,
            out=args.out, run_dir=args.run_dir, workers=args.workers,
            diag_port=args.diag, extra=args.extra)
    except (planeview.PlaneRowError, ValueError) as error:
        print(f"PLANE VIEW REFUSED: {error}", file=sys.stderr)
        return 1
    try:
        seams = planeview.verify_seams()
    except planeview.SeamError as error:
        print(f"SEAM CHECK FAILED: {error}", file=sys.stderr)
        return 1
    print(f"plane-view row  {decode_plan.plane_ref}")
    print(f"source row      {decode_plan.source_ref}")
    for seam in seams:
        print(f"  seam ok       {seam}")
    print("  holo3 " + " ".join(decode_plan.argv))
    if args.dry_run:
        if args.manifest is not None:
            Path(args.manifest).parent.mkdir(parents=True, exist_ok=True)
            Path(args.manifest).write_text(json.dumps({
                "plane_view_ref": decode_plan.plane_ref,
                "source_ref": decode_plan.source_ref,
                "stream_id": args.plane,
                "argv": list(decode_plan.argv),
                "row": decode_plan.row_report,
                "seams": list(seams),
            }, indent=2, sort_keys=True), "utf-8")
        return 0
    code = planeview.run(
        args.format_ref, args.plane, args.scans, args.dpi, out=args.out,
        run_dir=args.run_dir, workers=args.workers, diag_port=args.diag,
        extra=args.extra, manifest=args.manifest)
    if code == planeview.EXPECTED_NO_CLOSE_CODE:
        # holo3 says NOT RECOVERED because the close is deferred by
        # construction (--no-close); the certificates are in the run dir.
        print("plane view finished with the close deferred (holo3 exit "
              f"{code}); read the certificates from the run dir")
        return 0
    return code


def cmd_report(args: Any) -> int:
    stats = ledger_mod.ReadStats()
    header = ledger_mod.read_header(args.ledger)
    summary = ledger_mod.summarize(
        ledger_mod.iter_rows_latest(args.ledger, stats=stats), header=header)
    if stats.truncated_lines:
        print(f"{args.ledger}: {stats.truncated_lines} truncated line(s) "
              f"skipped — this ledger's pass did not finish",
              file=sys.stderr)
    if args.out is not None:
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / "summary.md").write_text(summary, "utf-8")
    print(summary)
    return 0


def cmd_union_base(args: Any) -> int:
    try:
        record = unionbase_mod.build(args.run_dir, args.facts, args.out,
                                     verify_facts=bool(args.verify_facts))
    except unionbase_mod.UnionBaseError as error:
        print(f"UNION BASE REFUSED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(record, indent=2, sort_keys=True))
    print(f"{args.out}: {len(record['symlinked'])} symlink(s), facts -> "
          f"{record['facts']}")
    return 0


def cmd_score(args: Any) -> int:
    """The ONE door that opens a payload — and it decodes nothing."""
    from . import score as score_mod
    try:
        header = score_mod.score(
            args.ledgers, args.payload, args.out, gt_dir=args.gt_dir,
            run_dir=args.run_dir, format_ref=args.format_ref,
            config=_config(args), limit=args.limit,
            n_pages=args.pages)
    except (score_mod.ScoreError, truth_error()) as error:
        print(f"SCORE REFUSED: {error}", file=sys.stderr)
        return 1
    print(header["report"])
    if args.maps:
        _header, rows = ledger_mod.read_rows(Path(args.out)
                                             / score_mod.SCORE_ROWS)
        written = score_mod.render_maps(rows, args.out)
        print(f"maps: {len(written)} PNG(s) in {args.out}")
    if header["n_wrong"] or header["n_false_accept"]:
        print(f"CERTIFICATES DISAGREE WITH THE PAYLOAD: "
              f"{header['n_wrong']} wrong, {header['n_false_accept']} false "
              f"accept(s)", file=sys.stderr)
        return EXIT_WRONG
    return 0


def truth_error() -> type:
    """`analyzer.truth`'s error class, imported at CALL time.

    The scoring module is the only importer of `analyzer.truth` in the
    package, and `cmd_score` is the only place in this file that reaches
    it — a module-level import here would put truth on every run
    command's import graph, which is the thing the ruling forbids and
    the import-set test checks.
    """
    from . import truth as truth_mod
    return truth_mod.TruthError


COMMANDS = {"census": cmd_census, "read": cmd_read, "ladder": cmd_ladder,
            "controls": cmd_controls, "close": cmd_close,
            "mirror": cmd_mirror, "export-facts": cmd_export_facts,
            "union-base": cmd_union_base, "score": cmd_score,
            "emit-plane": cmd_emit_plane,
            "plane-view-decode": cmd_plane_view_decode,
            "report": cmd_report}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)
