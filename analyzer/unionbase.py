"""The union base — one run dir, another run's certificates (2026-09-04).

An analyzer pass reads a RUN DIR: `report.json` for capture identity,
`events.jsonl` for the format ref, `facts.npz` for placements and
certificates, and `<capture12>/l{NN}-{r,g,b}.npy` for the pixels.  Only
one of those five changes when a pass builds on the previous pass's
harvest — the facts — and the rasters are the expensive ones (tens of
gigabytes per sheet).  So an incremental pass does not copy a run dir
and does not re-decode anything: it gets a NEW dir whose rasters are
symlinks to the base run's and whose `facts.npz` is the exported snapshot
(`analyzer export-facts`) that already carries the earlier passes'
certificates.  `events.jsonl` is symlinked with the rasters (it is
hundreds of megabytes and never changes); `report.json` and `argv` are
copied, because they are small and a reader expects to find them, not
follow them.

WHAT IS VERIFIED, and why it has to be.  A snapshot carries POSES, and a
pose is meaningless against another capture's pixels: an exported
snapshot whose placements name captures this run dir does not hold would
point the sampler at the wrong rasters and produce evidence that looks
fine and means nothing.  So the capture ids the facts name are checked
against the ones `report.json` declares, and every declared capture's
raster directory must exist.  A mismatch REFUSES; nothing is written.

COST.  The verification reads the snapshot once (6.5 GB on sheet I,
about 12 GB on H) and drops it again, which is the price of not writing
a pointer to rasters it does not match.  The facts file is SYMLINKED,
not copied: deleting or rewriting `--facts` afterwards breaks every run
dir built from it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Sequence

from holo3 import snapshot

#: Copied verbatim from the base run dir (small; `argv` is optional).
COPIED: tuple[str, ...] = ("report.json", "argv")

#: Symlinked from the base run dir beside the raster directories.
LINKED: tuple[str, ...] = ("events.jsonl",)

#: Written beside the new dir's facts, saying what this tool did.
RECORD_NAME = "union-base.json"


class UnionBaseError(RuntimeError):
    """The union base refuses — nothing was written."""


def declared_captures(run_dir: Path | str) -> tuple[str, ...]:
    """The capture ids `report.json` declares, in its own order."""
    path = Path(run_dir) / "report.json"
    if not path.exists():
        raise UnionBaseError(f"{path} is absent — not a finished run dir")
    report = json.loads(path.read_text("utf-8"))
    return tuple(str(fact["capture"]) for fact in report["capture_facts"])


def facts_captures(facts: Sequence[Any]) -> tuple[str, ...]:
    """Every capture id the fact tuple names, sorted.

    Placements, plane fields and capture surveys all carry one; nothing
    else does, and a fact tuple that names none at all is a snapshot
    with no poses in it, which is not something to build a pass on.
    """
    seen = {str(getattr(fact, "capture_id")) for fact in facts
            if getattr(fact, "capture_id", None) is not None}
    return tuple(sorted(seen))


def _link(target: Path, link: Path) -> None:
    if link.is_symlink() or link.exists():
        link.unlink()
    os.symlink(os.path.abspath(target), link)


def build(run_dir: Path | str, facts_path: Path | str,
          out_dir: Path | str, *, verify_facts: bool = True) -> dict:
    """Build the union-base run dir; returns the record it writes."""
    run_dir = Path(run_dir)
    facts_path = Path(facts_path)
    out_dir = Path(out_dir)
    if not facts_path.exists():
        raise UnionBaseError(f"--facts {facts_path} is absent")
    if out_dir.resolve() == run_dir.resolve():
        raise UnionBaseError(
            f"--out {out_dir} is the base run dir; a union base is a NEW "
            f"dir, never an overwrite of the run it borrows from")

    captures = declared_captures(run_dir)
    missing_rasters = [name for name in captures
                       if not (run_dir / name[:12]).is_dir()]
    if missing_rasters:
        raise UnionBaseError(
            f"{run_dir} declares {len(captures)} capture(s) but has no "
            f"raster directory for: "
            + ", ".join(name[:12] for name in missing_rasters))

    in_facts: tuple[str, ...] = ()
    n_facts = None
    if verify_facts:
        facts = snapshot.read(facts_path)
        n_facts = len(facts)
        in_facts = facts_captures(facts)
        del facts
        if not in_facts:
            raise UnionBaseError(
                f"{facts_path} names no capture at all — a snapshot with "
                f"no poses is not a base for a pass")
        unknown = [name for name in in_facts if name not in captures]
        if unknown:
            raise UnionBaseError(
                f"{facts_path} carries poses for capture(s) "
                + ", ".join(name[:12] for name in unknown)
                + f", which {run_dir}/report.json does not declare: those "
                f"poses would be applied to another capture's pixels")

    out_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in COPIED:
        source = run_dir / name
        if not source.exists():
            if name == "argv":                       # provenance only
                continue
            raise UnionBaseError(f"{source} is absent")
        (out_dir / name).write_bytes(source.read_bytes())
        copied.append(name)
    linked: list[str] = []
    for name in LINKED:
        source = run_dir / name
        if not source.exists():
            raise UnionBaseError(f"{source} is absent")
        _link(source, out_dir / name)
        linked.append(name)
    for name in captures:
        _link(run_dir / name[:12], out_dir / name[:12])
        linked.append(name[:12])
    _link(facts_path, out_dir / snapshot.NAME)

    record = {
        "tool": "analyzer union-base",
        "base_run_dir": str(run_dir),
        "facts": str(facts_path),
        "facts_symlinked_as": str(out_dir / snapshot.NAME),
        "out": str(out_dir),
        "copied": copied,
        "symlinked": linked,
        "captures_declared": [name[:12] for name in captures],
        "captures_in_facts": [name[:12] for name in in_facts],
        "captures_verified": bool(verify_facts),
        "n_facts": n_facts,
    }
    (out_dir / RECORD_NAME).write_text(
        json.dumps(record, indent=2, sort_keys=True), "utf-8")
    return record


# ------------------------------------------------------- open-after targets

TARGET_PREFIX = "open-after "


def is_open_after(spec: str) -> bool:
    return str(spec).startswith(TARGET_PREFIX)


def certified_in(ledger_paths: Sequence[Path | str]) -> set:
    """Every key the given ledgers certified (either verdict).

    STREAMED, for the same reason `analyzer score` streams: a sheet-H
    pass is 2.6-5.8 GB of JSON and the five together are 18 GB, while
    what this function keeps is a few thousand 4-tuples.  Materialising
    the rows to select four fields out of each would cost tens of
    gigabytes of RSS for a set that fits in a megabyte.
    """
    from . import ledger as ledger_mod
    from .types import VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST

    out = set()
    for path in ledger_paths:
        path = Path(path)
        if not path.exists():
            raise UnionBaseError(f"ledger {path} is absent")
        for row in ledger_mod.iter_rows(path):
            if row.get("verdict") in (VERDICT_CERTIFIED,
                                      VERDICT_CERTIFIED_LIST):
                out.add((int(row["page"]), int(row["ty"]), int(row["tx"]),
                         str(row["stream_id"])))
    return out


def open_after(census_rows: Sequence[Any], spec: str) -> list:
    """`--targets 'open-after L1.jsonl,L2.jsonl'` (2026-09-04).

    The covered, uncertified keys AFTER the union of those ledgers and
    the run dir's own facts.  The second half is free — a union-base run
    dir already has the exported certificates in its snapshot, so the
    census calls them certified — and the first half is what makes an
    incremental pass targetable from ledgers that have NOT been exported
    yet, or from a pass run against the plain base dir.
    """
    from . import residue as residue_mod

    names = [name.strip() for name in spec[len(TARGET_PREFIX):].split(",")]
    paths = [name for name in names if name]
    if not paths:
        raise UnionBaseError(
            f"--targets {spec!r} names no ledger (spelling: "
            f"'open-after LEDGER[,LEDGER]')")
    done = certified_in(paths)
    return [row for row in residue_mod.residue_rows(census_rows)
            if row.key not in done]
