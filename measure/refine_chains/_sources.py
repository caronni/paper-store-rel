"""The archived runs this census reads, and where they live.

Historical record of the refinement-chain census (2026-09); inputs in
the evidence archive.

Every path is READ-ONLY evidence, RELATIVE to ``--evidence-root``
(``measure/_evidence.py``; the layout the census read:
``holo3-overnight-events/``, ``sheetI-20260831/``, ``page-domain-qual/``,
``sheetJ-20260902/`` and the two J run dirs at its top); the roster is `ARTEFACTS.md` §1's holo3 event streams and
run dirs.  None of them is in the published evidence archive (tier
delete, 2026-10-09: event journals and fact snapshots excluded by rule;
only the runs' argv/tree/report identity files are published), so
:data:`WITHDRAWN` names them for the census's refusal.

A run contributes a chain census from its event stream; it
contributes composed DRIFT only if a fact snapshot stands beside the
stream, because an adopted revision writes no event of its own — the
stream carries the accepted placement, the snapshot the final standing
pose.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: <worktree>/measure/refine_chains and the worktree root.
HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parent.parent

#: Relative to the evidence root.
OVERNIGHT = Path("holo3-overnight-events")
SHEET_I = Path("sheetI-20260831")
PAGE_DOMAIN = Path("page-domain-qual")
SHEET_J = Path("sheetJ-20260902")


#: Every input root the roster reads, by the record's own names — none
#: published.
WITHDRAWN = (OVERNIGHT, SHEET_I, PAGE_DOMAIN, SHEET_J,
             Path("J-run.52093*"), Path("J-run.54028*"))


@dataclass(frozen=True)
class Run:
    name: str
    volume: str
    events: Path
    facts: Path | None
    note: str


def _run_dir(parent: Path, prefix: str) -> tuple[Path | None, Path | None]:
    matches = sorted(parent.glob(f"{prefix}*"))
    for path in matches:
        if (path / "events.jsonl").is_file():
            facts = path / "facts.npz"
            return path / "events.jsonl", facts if facts.is_file() else None
    return None, None


def _dir_run(name: str, volume: str, parent: Path, prefix: str,
             note: str) -> Run | None:
    events, facts = _run_dir(parent, prefix)
    if events is None:
        return None
    return Run(name, volume, events, facts, note)


def _stream_run(name: str, volume: str, path: Path, note: str) -> Run | None:
    return Run(name, volume, path, None, note) if path.is_file() else None


def roster(root: Path) -> tuple[Run, ...]:
    """Every archived run under ``root``, missing ones dropped."""
    overnight, sheet_i = root / OVERNIGHT, root / SHEET_I
    page_domain, sheet_j = root / PAGE_DOMAIN, root / SHEET_J
    found = (
        _stream_run("e029", "e029 HP K", overnight / "e029-events.jsonl.xz",
                    "2026-08-30 baseline harvest"),
        _stream_run("e029-postfix", "e029 HP K",
                    overnight / "e029-postfix-events.jsonl.xz",
                    "2026-08-30 post-fix harvest"),
        _stream_run("xerox-k", "xerox K",
                    overnight / "xerox-k-events.jsonl.xz", "baseline"),
        _stream_run("xerox-k-postfix", "xerox K",
                    overnight / "xerox-k-postfix-events.jsonl.xz",
                    "post-fix"),
        _stream_run("c3-cmy7", "xerox c3-cmy7",
                    overnight / "c3-cmy7-events.jsonl.xz", "baseline"),
        _stream_run("c2-cmy8", "xerox c2-cmy8",
                    overnight / "c2-cmy8-events.jsonl.xz", "baseline"),
        _stream_run("c2-cmy7", "xerox c2-cmy7",
                    overnight / "c2-cmy7-events.jsonl.xz", "baseline"),
        _stream_run("sheet-I", "sheet I",
                    overnight / "sheet-I-events.jsonl.xz",
                    "run-7, the PARITY.md baseline"),
        _stream_run("sheetH-maxstack", "sheet H",
                    overnight / "sheetH-maxstack-events.jsonl.xz",
                    "seven captures"),
        _stream_run("sheetH-mixed", "sheet H",
                    overnight / "sheetH-mixed-events.jsonl.xz",
                    "four captures"),
        _stream_run("I-chain-1", "sheet I",
                    sheet_i / "events-first.jsonl.xz", "e034 run 1"),
        _stream_run("I-chain-2", "sheet I",
                    sheet_i / "events-resume.jsonl.xz", "e034 run 2"),
        _stream_run("I-chain-3", "sheet I",
                    sheet_i / "events-resume-2.jsonl.xz", "e034 run 3"),
        _stream_run("I-chain-4", "sheet I",
                    sheet_i / "events-resume-3.jsonl.xz", "e034 run 4"),
        _dir_run("pd-base", "e029 HP K", page_domain, "base-e029-run.",
                 "page-domain qualification, base"),
        _dir_run("pd-null", "e029 HP K", page_domain, "merged-null-run.",
                 "page-domain qualification, --pages 1"),
        _dir_run("pd-merged", "e029 HP K", page_domain,
                 "merged-default-run.", "page-domain qualification, merged"),
        _dir_run("J-run-1", "sheet J", root, "J-run.52093",
                 "e035 first run, one capture"),
        _dir_run("J-run-2", "sheet J", root, "J-run.54028",
                 "e035 resume, --pages 100"),
        _stream_run("J-arch-3", "sheet J",
                    sheet_j / "J-run.66853" / "events.jsonl.xz",
                    "e035 archived resume chain"),
        _stream_run("J-arch-4", "sheet J",
                    sheet_j / "J-run.68649" / "events.jsonl.xz",
                    "e035 archived resume chain"),
        _stream_run("J-arch-5", "sheet J",
                    sheet_j / "J-run.78759" / "events.jsonl.xz",
                    "e035 archived resume chain"),
        _stream_run("J-complete", "sheet J",
                    sheet_j / "J-run-complete.81777" / "events.jsonl.xz",
                    "e035 from-scratch --complete run"),
    )
    return tuple(run for run in found if run is not None)
