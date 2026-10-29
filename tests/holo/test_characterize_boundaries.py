"""Static ownership boundaries for the standalone characterization tool."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
HOLO_ROOT = SOURCE_ROOT / "holo"
# Gate E: "receive"/"holo.receive" left both tuples with the v1
# receiver.  A named package that is not on disk makes rglob return
# nothing, so the firewall would pass degraded — hence the source-count
# assertion in test_import_boundaries below.
PRODUCTION_PACKAGES = ("core", "devices", "format", "gen")
PRODUCTION_FORBIDDEN = (
    "holo.characterize",
    "holo.track2",
    "experiments",
    "paperholo",
)
CHARACTERIZE_FORBIDDEN = (
    "holo.core",
    "holo.devices",
    "holo.format",
    "holo.gen",
    "holo.track2",
    "experiments",
    "paperholo",
)


def _module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported_modules(path: Path) -> tuple[tuple[int, str], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module = _module_name(path)
    package_parts = module.split(".")
    if path.name != "__init__.py":
        package_parts.pop()

    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue

        if node.level:
            keep = len(package_parts) - node.level + 1
            base_parts = package_parts[:max(keep, 0)]
            if node.module:
                base_parts.extend(node.module.split("."))
            base = ".".join(base_parts)
        else:
            base = node.module or ""

        if base:
            imports.append((node.lineno, base))
        imports.extend(
            (node.lineno, ".".join(part for part in (base, alias.name)
                                   if part))
            for alias in node.names
        )
    return tuple(imports)


def _crossings(
    paths: tuple[Path, ...],
    forbidden: tuple[str, ...],
) -> tuple[str, ...]:
    found: list[str] = []
    for path in paths:
        for line, imported in _imported_modules(path):
            if any(
                imported == prefix or imported.startswith(f"{prefix}.")
                for prefix in forbidden
            ):
                relative = path.relative_to(REPOSITORY_ROOT)
                found.append(f"{relative}:{line}: imports {imported}")
    return tuple(found)


def _production_sources() -> tuple[Path, ...]:
    missing = [package for package in PRODUCTION_PACKAGES
               if not (HOLO_ROOT / package).is_dir()]
    assert not missing, f"PRODUCTION_PACKAGES names absent packages: {missing}"
    return tuple(
        path
        for package in PRODUCTION_PACKAGES
        for path in sorted((HOLO_ROOT / package).rglob("*.py"))
        if "qualification" not in path.relative_to(HOLO_ROOT).parts
    )


def _paperholo_sources() -> tuple[Path, ...]:
    return tuple(sorted((SOURCE_ROOT / "paperholo").rglob("*.py")))


def _characterize_sources() -> tuple[Path, ...]:
    root = HOLO_ROOT / "characterize"
    return tuple(sorted(root.rglob("*.py"))) if root.is_dir() else ()


@pytest.mark.parametrize(
    ("paths", "forbidden"),
    (
        (_production_sources(), PRODUCTION_FORBIDDEN),
        (_paperholo_sources(), ("holo.characterize", "holo.track2")),
        (_characterize_sources(), CHARACTERIZE_FORBIDDEN),
    ),
    ids=(
        "production-does-not-own-characterization",
        "paperholo-does-not-own-characterization",
        "characterization-does-not-own-production",
    ),
)
def test_import_boundaries(
    paths: tuple[Path, ...],
    forbidden: tuple[str, ...],
) -> None:
    # A firewall over an empty file set proves nothing; every side of
    # this boundary is a real tree with real modules.
    assert len(paths) >= 5, f"only {len(paths)} sources to sweep"
    assert _crossings(paths, forbidden) == ()


def test_characterization_enters_production_only_at_cli_composition_root(
) -> None:
    entry_sources = tuple(sorted(HOLO_ROOT.glob("*.py")))
    crossings = _crossings(entry_sources, ("holo.characterize",))

    assert crossings
    assert all(
        crossing.startswith("src/holo/cli.py:")
        for crossing in crossings
    )

