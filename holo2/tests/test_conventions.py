"""House rules enforced as tests (DESIGN L11/L12; WORKPLAN standing rules).

Headless receiver paths read no clocks, library code contains no RNG, no
file outgrows the 1000-line cap, and dependencies stay inside the
declared project set.

The dependency fence is against NEW third-party packages, not against
the stdlib: stdlib membership is asked of ``sys`` rather than kept as a
hand-maintained list (which turned into a treadmill as H2 leaves landed),
and the third-party names are exactly the repo's declared
``requirements.txt`` runtime set that receiver code may use.
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest
from _srctree import SRC, sources

_SOURCES = sources(SRC.parent)

_CLOCKS = re.compile(
    r"\btime\.\w+|perf_counter|monotonic|process_time|datetime|\btime_ns\b"
    r"|import\s+time\b")
# ``seed(`` catches ``np.random.seed(...)`` / ``rng.seed(...)``.  A *def* of
# something called ``seed`` is not a draw: format v1's per-row keystream
# address seed is spelled ``seed`` everywhere on the format surface
# (HOLO-DESIGN §4.5, and the carried tile chain reads ``spec.seed``), so the
# accessor is excluded by name — the calls it would have caught are not.
_RNG = re.compile(
    r"\bimport\s+random\b|\brandom\.\w+|default_rng|RandomState"
    r"|(?<!def )\bseed\(")
# The ``from`` arm requires the ``import`` keyword: without it a wrapped
# docstring line ("… a level is never resized\nfrom another level.") reads
# as an import of module ``another``.  Relative imports start with "." and
# so never match the leading ``[A-Za-z_]``.
_THIRD_PARTY = re.compile(
    r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import\b"
    r"|import\s+([A-Za-z_][\w.]*))")

# Declared runtime dependencies (requirements.txt) that receiver code may
# import: numpy/scipy core, the pillow/tifffile decoders for capture
# ingest, cryptography for the AES-CTR address keystream.  Anything else
# third-party is a new dependency and needs a user ruling, not a test edit.
_THIRD_PARTY_OK = {"numpy", "scipy", "PIL", "tifffile", "cryptography"}
_ALLOWED = _THIRD_PARTY_OK | set(sys.stdlib_module_names)
#: The repo root: ``holo2/tests`` -> ``holo2`` -> here.
_ROOT = Path(__file__).resolve().parents[2]

#: A read of the authenticated raster's own pixels.  ``crop_luma`` and
#: ``crop_native`` are the only two ways to get any (``capture/scan.py``),
#: which is what makes an allowlist over them exact rather than indicative.
_RAW_PIXELS = re.compile(r"\.crop_luma\(|\.crop_native\(")
#: DESIGN §6.8 stage 3, as data: the modules entitled to read RAW capture
#: pixels.  Everything else reads the region's PREPARED plane through a
#: view, which is why the raw raster is a preparation input and not a
#: per-fire working set.  The list was prose in §6.8's conformance
#: inventory until it went stale under W1a (the pre-doctrine payload crop
#: died with ``placement_h3bis`` and the inventory still named it), so it
#: is a test now.  A new row is a doctrine change and reads as one.
_RAW_PIXEL_READERS = {
    # ingest: the E021 survey's bounded tile crops, and the accessor itself
    "capture/_survey_tensor.py", "capture/scan.py",
    # ingest: the four platen borders, read ONCE where the pixels already
    # are and written to the capture record (2026-08-17). It joins the
    # list on §6.8's own terms — this IS the ingest row — and the reason
    # it had to move here from the session is that a resume without the
    # file cannot compute the scalar its prepared planes are named by.
    "capture/ingest.py",
    # preparation: the platen-backing borders, and v1's whole-region
    # oracle that ``prepared.py`` streams byte-identically
    "solve/pose_fit.py",
    # preparation: the streaming build of the file-backed plane
    "solve/prepared.py",
    # EXEMPT (§6.8): the observer's underlay, small and observer-side
    "diag/panes/model.py",
}


def test_sources_exist() -> None:
    assert len(_SOURCES) >= 8


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: p.name)
def test_no_clock_reads(path: Path) -> None:
    hits = [f"{path.name}:{n}: {line.strip()}"
            for n, line in enumerate(path.read_text().splitlines(), start=1)
            if _CLOCKS.search(line)]
    assert not hits, "headless paths read no clocks (L12):\n" + "\n".join(hits)


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: p.name)
def test_no_rng(path: Path) -> None:
    hits = [f"{path.name}:{n}: {line.strip()}"
            for n, line in enumerate(path.read_text().splitlines(), start=1)
            if _RNG.search(line)]
    assert not hits, "H1 contains no RNG:\n" + "\n".join(hits)


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: p.name)
def test_only_declared_dependencies(path: Path) -> None:
    imported = {(match.group(1) or match.group(2)).split(".")[0]
                for match in (_THIRD_PARTY.match(line)
                              for line in path.read_text().splitlines())
                if match is not None} - {"holo2"}
    assert imported <= _ALLOWED, (
        f"{path.name}: undeclared dependency {sorted(imported - _ALLOWED)}")


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: p.name)
def test_raw_pixel_reads_stay_on_the_prepared_path(path: Path) -> None:
    """§6.8: fires read prepared planes; only ingest and preparation crop."""
    where = path.relative_to(SRC).as_posix()
    hits = [f"{where}:{n}: {line.strip()}"
            for n, line in enumerate(path.read_text().splitlines(), start=1)
            if _RAW_PIXELS.search(line)]
    assert not hits or where in _RAW_PIXEL_READERS, (
        "raw capture pixels are read at ingest and at region preparation "
        "only (DESIGN §6.8); everything else reads the prepared plane "
        "through a view:\n" + "\n".join(hits))


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: p.name)
def test_file_length_cap(path: Path) -> None:
    lines = len(path.read_text().splitlines())
    assert lines <= 1000, f"{path.name}: {lines} lines (cap 1000)"


#: The by-path measurement drivers: the top-level ``holo2/measure/*.py``
#: scripts, non-recursive on purpose — ``verdicts/`` is pytest-collected
#: (by itself, per its README) and needs no guard.  The scripts live
#: outside ``testpaths``, carry no ``test_`` names and end in ``__main__``
#: blocks; see ``holo2/measure/README.md`` for what each one is FOR.
_MEASURE = _ROOT / "holo2" / "measure"
_MEASURE_SCRIPTS = sorted(_MEASURE.glob("*.py"))
#: Where a script's bare sibling imports resolve: every script inserts
#: its own directory's ``verdicts/`` onto ``sys.path`` before importing
#: ``_fixtures`` / ``conftest``, and ``bch_equivalence.py`` imports its
#: two population modules as plain siblings.
_MEASURE_SIBLINGS = (_MEASURE, _MEASURE / "verdicts")
#: First-party roots a measure script may import, and where each one's
#: source lives.  ``holo`` is LEGAL there — the measure tree is the
#: bridge root the firewall's own docstring names (pages emitted by the
#: real v1 generator, decoded by holo2) — and resolving it statically
#: keeps this suite free of any actual ``holo`` import.
_MEASURE_ROOTS = {
    "holo2": _ROOT / "holo2" / "src" / "holo2",
    "holo": _ROOT / "src" / "holo",
    "paperholo": _ROOT / "src" / "paperholo",
}
#: Measure drivers are operator tooling, not receiver code: pytest is
#: allowed on top of the declared runtime set.  Anything further is a
#: new dependency and needs a user ruling, exactly as above.
_MEASURE_THIRD_PARTY = _THIRD_PARTY_OK | {"pytest"}


def _module_file(module: str) -> Path | None:
    """The source file a dotted first-party module name denotes."""
    parts = module.split(".")
    base = _MEASURE_ROOTS[parts[0]].joinpath(*parts[1:])
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _bound_names(path: Path) -> set[str]:
    """Names a module binds at top level, statically.

    Defs, classes, assignment targets and import aliases, following
    ``if``/``try`` bodies (a conditional re-export is still a binding).
    Function bodies are never entered, so nothing here executes and no
    local leaks in.
    """
    names: set[str] = set()
    pending = [ast.parse(path.read_text(encoding="utf-8")).body]
    while pending:
        for node in pending.pop():
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names.update((alias.asname or alias.name).split(".")[0]
                             for alias in node.names)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target])
                for target in targets:
                    names.update(n.id for n in ast.walk(target)
                                 if isinstance(n, ast.Name))
            elif isinstance(node, (ast.If, ast.Try)):
                pending.append(node.body)
                pending.append(node.orelse)
                pending.extend(h.body for h in getattr(node, "handlers", ()))
                pending.append(getattr(node, "finalbody", []))
    return names


def _unresolved(module: str, names: tuple[str, ...]) -> list[str]:
    """Which of one import statement's targets no longer exist."""
    root = module.split(".")[0]
    if root in sys.stdlib_module_names or root in _MEASURE_THIRD_PARTY:
        return []
    if root in _MEASURE_ROOTS:
        file = _module_file(module)
        if file is None:
            return [f"no module {module!r}"]
    else:
        for directory in _MEASURE_SIBLINGS:
            if (directory / f"{root}.py").is_file():
                file = directory / f"{root}.py"
                break
        else:
            return [f"unresolvable root {root!r} (module {module!r}): not "
                    "stdlib, not a declared third-party name, not a sibling"]
    bound = _bound_names(file)
    package_dir = file.parent if file.name == "__init__.py" else None
    return [f"from {module} import {name}" for name in names
            if name != "*" and name not in bound
            and not (package_dir
                     and ((package_dir / f"{name}.py").is_file()
                          or (package_dir / name / "__init__.py").is_file()))]


def test_measure_scripts_exist() -> None:
    assert len(_MEASURE_SCRIPTS) >= 8


@pytest.mark.parametrize("path", _MEASURE_SCRIPTS, ids=lambda p: p.name)
def test_measure_script_imports_resolve(path: Path) -> None:
    """Every import in a by-path measure script still names something real.

    Nothing under ``testpaths`` imports ``holo2/measure``'s top-level
    scripts — deliberately: they are ``__main__`` drivers off the
    suite's clock (measure/README.md).  The price of that freedom is
    that a rename in ``src`` can break an acceptance instrument while
    the whole suite stays green, and did: H4 W6 renamed
    ``solve.payload_h3bis`` to ``solve.payload`` (2026-08-18) and
    ``or5_or7_census.py`` — the instrument H5's re-work aging was then
    accepted on — raised ImportError on every invocation until the H5
    build tripped over it and repaired it (2026-08-19).

    The scripts are RESOLVED, never executed.  Executing them is not an
    option even though their module levels are only imports and
    constants: ``_w4_cold_probe.py`` imports ``conftest`` (meaning
    ``verdicts/conftest.py``), which run here would collide with
    ``holo2/tests/conftest.py`` in ``sys.modules`` — the exact trap
    ``test_test_module_basenames_are_unique`` exists for.  So the guard
    reads each script's import statements from the AST and checks them
    statically: first-party targets against the source tree (the module
    file must exist, and every ``from`` name must be a top-level binding
    or a submodule), sibling targets against the sibling's own top-level
    bindings; stdlib and the declared third-party set are trusted.  A
    pass means every name still resolves — not that the script still
    measures what its docstring says it does.
    """
    problems: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                problems += [f"line {node.lineno}: {hit}"
                             for hit in _unresolved(alias.name, ())]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                problems.append(f"line {node.lineno}: relative import in a "
                                "by-path script")
                continue
            problems += [f"line {node.lineno}: {hit}" for hit in _unresolved(
                node.module or "", tuple(a.name for a in node.names))]
    assert not problems, (
        f"{path.name}: stale imports — the script would die at import time "
        "when run by path:\n" + "\n".join(problems))


def test_test_module_basenames_are_unique() -> None:
    """No two modules under ``testpaths`` share a basename, repo-wide.

    Pytest's prepend import mode — which holo2's own suite needs, since it
    imports ``conftest`` and ``_srctree`` as siblings — puts each test
    file's DIRECTORY on ``sys.path`` and imports by BASENAME alone, so one
    shared name anywhere under ``testpaths`` aborts the WHOLE repo's
    collection.  Only a full-repo ``pytest`` ever sees that; ``pytest
    holo2/tests`` and ``pytest tests/holo`` never do, which is how two
    collisions lurked unnoticed (2026-08-14).  holo2 is the tree that
    grows, so it owes the repo the check, placed in the suite that is
    actually run.  ``testpaths`` is READ, never restated.

    IT IS EVERY MODULE, NOT JUST ``test_*.py`` (widened 2026-08-15, H4
    W1b).  The glob used to be ``test_*.py``, which left the sibling
    modules the suites import by bare name — ``conftest``, ``_srctree``,
    ``_cli_kit``, ``_real_fixtures`` — outside the guard entirely.  That
    hole is not theoretical: adding a second ``conftest.py``, in the other
    testpath, shadowed ``holo2/tests/conftest.py`` in ``sys.modules`` and
    broke 23 files with ``ImportError: cannot import name 'CAPTURE_SHA'
    from 'conftest'`` — while both per-suite commands stayed green, which
    is precisely the failure mode this test exists to catch.
    """
    config = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    collisions, seen = [], {}
    for testpath in config["tool"]["pytest"]["ini_options"]["testpaths"]:
        for path in sorted((_ROOT / testpath).rglob("*.py")):
            # A package marker is never imported by basename.
            if path.name == "__init__.py":
                continue
            first = seen.setdefault(path.name, path)
            if first != path:
                collisions.append(f"{first.relative_to(_ROOT)} vs "
                                  f"{path.relative_to(_ROOT)}")
    assert not collisions, (
        "a full-repo pytest aborts at collection on:\n" + "\n".join(collisions))
