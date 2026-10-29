"""Rebuild a finished run dir's rasters on local disk — PLAN §6.

A holo3 run dir is five things: `argv`, `report.json`, `events.jsonl`,
`facts.npz`, and one `<capture12>/l{NN}-{r,g,b}.npy` directory per
capture.  The first four are megabytes and travel; the raster
directories are gigabytes and often sit on a network mount where the
analyzer's mmap reads are too slow to use (sheet I's four captures are
~9 GB of `.npy`).

This module reconstructs those directories LOCALLY, from the capture
TIFFs, by calling `holo.receiver.plugins.intake.ingest_capture` — the same
function production called — so the products are byte-identical to the
originals rather than merely equivalent.  Nothing here decodes: the
placements, certificates and close all come from the source
`facts.npz`/`report.json` unchanged.

WHAT IT TRUSTS.  The source `argv` names the captures and their `--dpi`
(holo3 requires exactly one `--dpi` per scan, `src/holo/receiver/cli.py:85`); the
format row gives `pitch_in` and the family, which is all
`ingest_capture` needs beyond the pixels.  `report.json` is the
CHECKED-AGAINST truth: the capture ids, their declared `levels_ppc` and
`shape_yx` must all come back out, or the mirror refuses.

SEQUENTIAL BY RULING, NOT BY LIMITATION.  `ingest_capture` is
thread-safe as written (per-capture output directory, no shared mutable
state; `area_decimate_into` is a pure chunk loop), but each capture
holds its whole native raster: sheet I's 4800 capture is 56128x40832x3
= 6.8 GB.  Two at once does not fit beside anything else on this
machine, so captures are mirrored one at a time.

IDEMPOTENT.  A capture whose directory already holds every level of
every plane at the declared shape is SKIPPED without hashing the TIFF —
the run is re-runnable after an interruption at the cost of a few `.npy`
header reads.
"""

from __future__ import annotations

import shlex
import shutil
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from holo.receiver.format import identity
from holo.receiver.plugins import intake

from .inputs import InputsError, read_report, read_run_open

#: The repo root — relative capture paths in `argv` are relative to it.
REPO = Path(__file__).resolve().parents[1]

#: The four small files that define a run dir; copied when absent.
MIRROR_FILES: tuple[str, ...] = ("argv", "report.json", "events.jsonl",
                                 "facts.npz")

#: Of those, the small ones that IDENTIFY the run; a standing copy that
#: disagrees with a reachable source means `--out` is another run's dir.
IDENTITY_FILES: tuple[str, ...] = ("argv", "report.json")

#: What a capture positional looks like (`intake.load_native` reads all).
IMAGE_SUFFIXES: tuple[str, ...] = (".tif", ".tiff", ".png", ".jpg", ".jpeg")

#: `src/holo/receiver/cli.py` decode options that consume the following token, plus
#: `--pages`, which older run dirs' argv carry (sheet J's does) and the
#: current parser no longer has — hence this table rather than holo3's
#: own parser, which would refuse to read its own history.
VALUE_OPTIONS: frozenset[str] = frozenset({
    "--dpi", "--format", "--coding", "--printer", "--max-pages", "--out",
    "--workers", "--diag", "--run-dir", "--resume", "--pages",
})


class MirrorError(RuntimeError):
    """The mirror cannot reproduce what the source run dir declares."""


@dataclass(frozen=True)
class CapturePlan:
    """One capture to rebuild: what argv says and what the report says."""

    ordinal: int
    path: Path
    dpi: float
    capture_id: str
    sha12: str
    levels_ppc: tuple[str, ...]
    shape_yx: tuple[int, int]
    channels: int


# ------------------------------------------------------------ argv parsing

def parse_decode_argv(text: str) -> tuple[tuple[str, ...],
                                          tuple[float, ...]]:
    """The capture names and the `--dpi` values of a decode `argv`.

    Positional after `decode`, in order; every one must carry an image
    suffix (an unrecognised positional is named, never guessed past).
    """
    tokens = shlex.split(text.strip())
    try:
        start = tokens.index("decode") + 1
    except ValueError:
        raise MirrorError(
            f"argv is not a holo3 decode command line: {text.strip()[:120]}")
    scans: list[str] = []
    dpis: list[float] = []
    index = start
    while index < len(tokens):
        token = tokens[index]
        name, sep, inline = token.partition("=")
        if token.startswith("-") and name in VALUE_OPTIONS:
            if sep:
                value, index = inline, index + 1
            else:
                if index + 1 >= len(tokens):
                    raise MirrorError(f"argv option {name} has no value")
                value, index = tokens[index + 1], index + 2
            if name == "--dpi":
                dpis.append(float(value))
            continue
        if token.startswith("-"):
            index += 1
            continue
        if Path(token).suffix.lower() not in IMAGE_SUFFIXES:
            raise MirrorError(
                f"argv positional {token!r} is neither an option nor an "
                f"image ({IMAGE_SUFFIXES}); the mirror will not guess")
        scans.append(token)
        index += 1
    if len(scans) != len(dpis):
        raise MirrorError(
            f"argv names {len(scans)} capture(s) but {len(dpis)} --dpi "
            f"value(s); holo3 requires exactly one per scan")
    if not scans:
        raise MirrorError("argv names no captures")
    return tuple(scans), tuple(dpis)


def resolve_capture_path(name: str, *, tiff_dir: Path | None = None,
                         repo: Path = REPO) -> Path:
    """Where the capture named in `argv` actually is.

    `--tiff-dir` overrides the DIRECTORY only — the basename still comes
    from argv, so the sha (and therefore the capture id) cannot drift by
    renaming.  A relative argv path resolves against the repo root,
    which is where holo3 was run from.
    """
    given = Path(name)
    if tiff_dir is not None:
        path = Path(tiff_dir) / given.name
    elif given.is_absolute():
        path = given
    else:
        path = Path(repo) / given
    if not path.exists():
        raise MirrorError(f"capture {name!r} not found at {path}")
    return path


# --------------------------------------------------------- the small files

def copy_run_files(src_run_dir: Path, out_run_dir: Path) -> tuple[str, ...]:
    """Copy whichever of the four small files `out` is missing.

    A file already in `out` is KEPT, so an interrupted mirror resumes
    even when the source has since gone away — but the two identity
    files are compared when the source is reachable, because a re-`--out`
    onto another run's directory would otherwise mirror the wrong
    captures into it silently.  `facts.npz`/`events.jsonl` are not
    compared (sheet I's `facts.npz` is 228 MB); `report.json` is the
    file the whole pairing and verification is checked against, so a
    match there is the one that matters.
    """
    src_run_dir, out_run_dir = Path(src_run_dir), Path(out_run_dir)
    out_run_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in MIRROR_FILES:
        target = out_run_dir / name
        source = src_run_dir / name
        if target.exists():
            if (name in IDENTITY_FILES and source.exists()
                    and source.read_bytes() != target.read_bytes()):
                raise MirrorError(
                    f"{target} already holds a DIFFERENT {name} than "
                    f"{source}: --out is another run's directory, and the "
                    f"mirror will not blend two runs")
            continue
        if not source.exists():
            raise MirrorError(f"{source} is absent and {target} does not "
                              f"hold a copy")
        shutil.copyfile(source, target)
        copied.append(name)
    return tuple(copied)


# ------------------------------------------------------------- completeness

def level_plane_names(channels: int, family: identity.Family,
                      levels: Sequence[Any], index: int) -> tuple[str, ...]:
    """The plane files `ingest_capture` writes for one level.

    The NATIVE level (the last) is copied channel by channel
    (`intake.native_plane_names`); every coarser level is decimated into
    `intake.derived_planes`, which for cmy8 is the same r/g/b triple.
    """
    if index == levels[-1].index:
        return intake.native_plane_names(channels)
    return tuple(name for name, _channel in
                 intake.derived_planes(channels, family))


def capture_complete(plane_dir: Path, channels: int,
                     family: identity.Family,
                     levels: Sequence[Any]) -> bool:
    """Every level of every plane present at the level's declared shape."""
    if not plane_dir.is_dir():
        return False
    for level in levels:
        for plane in level_plane_names(channels, family, levels, level.index):
            path = intake.plane_path(plane_dir, level.index, plane)
            if not path.exists():
                return False
            try:
                shape = np.load(path, mmap_mode="r").shape
            except Exception:
                return False
            if tuple(int(value) for value in shape) != tuple(
                    int(value) for value in level.shape_px):
                return False
    return True


# ---------------------------------------------------------------- planning

def plan_captures(report: dict, scans: Sequence[str],
                  dpis: Sequence[float], *,
                  tiff_dir: Path | None = None) -> tuple[CapturePlan, ...]:
    """Pair the argv captures with `report.json`'s capture facts.

    holo3 de-duplicates by sha; the mirror de-duplicates by resolved
    path first (it has not hashed anything yet) and then REQUIRES the
    two counts to agree, so a silent pairing by position can never
    survive a duplicate.
    """
    facts = sorted(report.get("capture_facts") or (),
                   key=lambda fact: int(fact["ordinal"]))
    if not facts:
        raise MirrorError("report.json declares no capture_facts")
    seen: dict[Path, None] = {}
    paired: list[tuple[Path, float]] = []
    for name, dpi in zip(scans, dpis):
        path = resolve_capture_path(name, tiff_dir=tiff_dir)
        if path in seen:
            continue
        seen[path] = None
        paired.append((path, float(dpi)))
    if len(paired) != len(facts):
        raise MirrorError(
            f"argv names {len(paired)} distinct capture(s) "
            f"{[p.name for p, _ in paired]} but report.json declares "
            f"{len(facts)} ({[str(f['capture'])[:12] for f in facts]}); "
            f"the mirror will not pair them by position")
    plans: list[CapturePlan] = []
    for (path, dpi), fact in zip(paired, facts):
        if abs(float(fact["dpi"]) - dpi) > 1e-9:
            raise MirrorError(
                f"capture {path.name}: argv declares --dpi {dpi}, "
                f"report.json ordinal {fact['ordinal']} declares "
                f"{float(fact['dpi'])}")
        capture_id = str(fact["capture"])
        plans.append(CapturePlan(
            ordinal=int(fact["ordinal"]), path=path, dpi=dpi,
            capture_id=capture_id, sha12=capture_id[:12],
            levels_ppc=tuple(str(value) for value in fact["levels_ppc"]),
            shape_yx=(int(fact["shape_yx"][0]), int(fact["shape_yx"][1])),
            channels=int(fact["channels"])))
    return tuple(plans)


# --------------------------------------------------------------- the mirror

def verify_run_dir(out_run_dir: Path, report: dict, pitch_in: Fraction,
                   family: identity.Family) -> list[dict]:
    """Every capture `report.json` names is present, whole and the right
    shape.  Raises :class:`MirrorError` on the first disagreement."""
    out_run_dir = Path(out_run_dir)
    facts = {str(fact["capture"])[:12]: fact
             for fact in (report.get("capture_facts") or ())}
    rows: list[dict] = []
    for entry in report.get("captures") or ():
        sha12 = str(entry["sha12"])
        fact = facts.get(sha12)
        if fact is None:
            raise MirrorError(
                f"report.json names capture {sha12} in `captures` but "
                f"carries no capture_facts row for it")
        shape_yx = (int(fact["shape_yx"][0]), int(fact["shape_yx"][1]))
        channels = int(fact["channels"])
        levels = intake.build_levels(float(fact["dpi"]), pitch_in, shape_yx)
        declared = tuple(str(value) for value in fact["levels_ppc"])
        built = tuple(str(level.ppc) for level in levels)
        if built != declared:
            raise MirrorError(
                f"capture {sha12}: report declares levels {declared} but "
                f"intake.build_levels at pitch {pitch_in} gives {built}")
        plane_dir = out_run_dir / sha12
        if not plane_dir.is_dir():
            raise MirrorError(f"capture {sha12}: {plane_dir} is absent")
        for level in levels:
            for plane in level_plane_names(channels, family, levels,
                                           level.index):
                path = intake.plane_path(plane_dir, level.index, plane)
                if not path.exists():
                    raise MirrorError(
                        f"capture {sha12}: raster {path} is absent")
                shape = tuple(int(value) for value in
                              np.load(path, mmap_mode="r").shape)
                want = tuple(int(value) for value in level.shape_px)
                if shape != want:
                    raise MirrorError(
                        f"capture {sha12}: {path.name} is {shape}, the "
                        f"level declares {want}")
        native = tuple(int(value) for value in levels[-1].shape_px)
        if native != shape_yx:
            raise MirrorError(
                f"capture {sha12}: native level {native} != report "
                f"shape_yx {shape_yx}")
        rows.append({"sha12": sha12, "ordinal": int(fact["ordinal"]),
                     "dpi": float(fact["dpi"]), "levels": list(built),
                     "shape_yx": list(shape_yx), "channels": channels})
    if not rows:
        raise MirrorError("report.json names no captures to verify")
    return rows


def mirror(src_run_dir: Path | str, out_run_dir: Path | str, *,
           format_ref: str | None = None,
           tiff_dir: Path | str | None = None,
           log: Callable[[str], None] = print) -> dict:
    """Rebuild `out_run_dir` from `src_run_dir` plus the capture TIFFs."""
    src_run_dir = Path(src_run_dir)
    out_run_dir = Path(out_run_dir)
    if out_run_dir.resolve() == src_run_dir.resolve():
        raise MirrorError(
            f"--src-run-dir and --out are the same directory "
            f"({out_run_dir}); the mirror never writes into its source")
    copied = copy_run_files(src_run_dir, out_run_dir)
    if copied:
        log(f"copied {', '.join(copied)} from {src_run_dir}")

    report = read_report(out_run_dir)
    try:
        run_open = read_run_open(out_run_dir)
    except InputsError as error:
        raise MirrorError(str(error)) from error
    declared_ref = str(run_open["format_id"])
    used_ref = str(format_ref) if format_ref else declared_ref
    row = identity.resolve_format_ref(used_ref)
    if format_ref:
        log(f"format ref override: {declared_ref} -> {used_ref}")
    pitch_in = Fraction(row.pitch_in)

    argv_text = (out_run_dir / "argv").read_text("utf-8")
    scans, dpis = parse_decode_argv(argv_text)
    plans = plan_captures(report, scans, dpis,
                          tiff_dir=None if tiff_dir is None
                          else Path(tiff_dir))

    built: list[dict] = []
    for plan in plans:
        levels = intake.build_levels(plan.dpi, pitch_in, plan.shape_yx)
        plane_dir = out_run_dir / plan.sha12
        started = time.monotonic()
        if capture_complete(plane_dir, plan.channels, row.family, levels):
            log(f"{plan.sha12}  dpi {plan.dpi:g}  levels "
                f"{','.join(plan.levels_ppc)}  skipped (complete)")
            built.append({"sha12": plan.sha12, "ordinal": plan.ordinal,
                          "dpi": plan.dpi, "levels": list(plan.levels_ppc),
                          "seconds": 0.0, "ingested": False,
                          "path": str(plan.path)})
            continue
        capture, rasters, _events = intake.ingest_capture(
            plan.path, plan.dpi, pitch_in, row.family, out_run_dir,
            plan.ordinal)
        seconds = time.monotonic() - started
        if capture.capture_id != plan.capture_id:
            raise MirrorError(
                f"{plan.path} hashes to {capture.capture_id[:12]} but "
                f"report.json ordinal {plan.ordinal} declares "
                f"{plan.sha12} — that is a different capture")
        log(f"{plan.sha12}  dpi {plan.dpi:g}  levels "
            f"{','.join(str(level.ppc) for level in capture.levels)}  "
            f"{seconds:.1f} s  ({len(rasters)} rasters)")
        built.append({"sha12": plan.sha12, "ordinal": plan.ordinal,
                      "dpi": plan.dpi,
                      "levels": [str(level.ppc) for level in capture.levels],
                      "seconds": round(seconds, 3), "ingested": True,
                      "path": str(plan.path)})

    verified = verify_run_dir(out_run_dir, report, pitch_in, row.family)
    log(f"verified {len(verified)} capture(s) in {out_run_dir}")
    return {
        "src_run_dir": str(src_run_dir),
        "run_dir": str(out_run_dir),
        "copied": list(copied),
        "format_ref": used_ref,
        "format_ref_declared": declared_ref,
        "pitch_in": str(pitch_in),
        "family": row.family.value,
        "captures": built,
        "verified": verified,
    }
