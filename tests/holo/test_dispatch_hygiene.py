"""FORMAT-SPACE dispatch hygiene: the retired forms stay retired.

Automates the residual checks of docs/FORMAT-SPACE-DISPATCH.md — the
review-time greps, pinned so a regression cannot land silently:

1. The privatized frozen singletons are never named outside
   src/holo/format/.
2. codec-id string comparison is never used as a dispatch key outside
   src/holo/format/ (codec_id remains an informative label).
3. Nothing calls ``scale_plan``/``_scale_plan`` with the retired
   ``codec_id=`` keyword (the P1 signature is (codec_family, n_streams))
   — anywhere, including the corpus-replay harness.
"""
from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "holo"
_TESTS = Path(__file__).resolve().parent


def _py_files(root: Path, *, exclude_format: bool) -> list[Path]:
    out = []
    for path in sorted(root.rglob("*.py")):
        if exclude_format and "format" in path.relative_to(root).parts[:1]:
            continue
        out.append(path)
    return out


def _offending_lines(path: Path, pattern: re.Pattern) -> list[str]:
    hits = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.split("#", 1)[0]
        if pattern.search(stripped):
            hits.append(f"{path.name}:{n}: {line.strip()}")
    return hits


def test_no_singleton_names_outside_format() -> None:
    pattern = re.compile(r"CMY[78]_P120_V0|CMY8_STREAMS|CMY7_FEC")
    hits = []
    for path in _py_files(_SRC, exclude_format=True):
        hits += _offending_lines(path, pattern)
    assert not hits, "\n".join(hits)


def test_no_codec_id_comparisons_outside_format() -> None:
    pattern = re.compile(r"codec_id\s*[!=]=|[!=]=\s*\S*\.?codec_id\b")
    hits = []
    for path in _py_files(_SRC, exclude_format=True):
        hits += _offending_lines(path, pattern)
    assert not hits, "\n".join(hits)


def test_no_retired_scale_plan_keyword() -> None:
    pattern = re.compile(r"scale_plan\s*\([^)]*codec_id\s*=")
    hits = []
    for root in (_SRC, _TESTS):
        for path in sorted(root.rglob("*.py")):
            if path.name == Path(__file__).name:
                continue
            text = path.read_text()
            if pattern.search(text):
                hits.append(str(path))
    assert not hits, hits
