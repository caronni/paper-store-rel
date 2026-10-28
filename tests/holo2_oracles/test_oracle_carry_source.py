"""Oracle: the H2a carries differ from their originals ONLY as declared.

The behavioural oracles compare outputs on fixtures; this one compares
the code itself. Each carried module is parsed, docstrings are stripped
(comments never enter the AST), and every top-level definition is
compared to its original by ``ast.dump``. Anything that differs, is
missing, or is new must appear in ``ADAPTATIONS`` below — so a future
edit that quietly changes a carried numeric path fails here even if no
fixture happens to notice.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
_HOLO = _ROOT / "src" / "holo" / "receive"
_HOLO2 = _ROOT / "holo2" / "src" / "holo2"

# holo2 module path, relative to the package root (R0 grouped the carries
# into packages; holo's side stays flat) -> (changed, removed, added)
# top-level names.  Empty tuples mean "byte-for-byte the same executable
# code".
ADAPTATIONS: dict[str, tuple[frozenset[str], frozenset[str], frozenset[str]]] = {
    "capture/scan.py": (frozenset(), frozenset(), frozenset()),
    # C3 (RULINGS G4, 2026-08-22): the footing ladder takes the printed
    # PITCH and multiplies by the capture's dpi where the source takes a
    # dot count and divides by a hard-coded ``_PRINT_DPI = 600``.  The
    # engine grid is an assumption about a PRINTER made inside a
    # measurement of a SCAN, and a receiver cannot check it; the values
    # are identical wherever the source's form applied, which
    # ``test_oracle_scale_space.py`` proves rung by rung over the whole
    # (dpi, pitch) grid it is parametrized on.
    "capture/scale_space.py": (
        frozenset({"native_pixels_per_cell", "auto_ppc_levels",
                   "ScaleSchedule"}),
        frozenset({"_PRINT_DPI"}),
        frozenset(),
    ),
    "capture/lattice.py": (frozenset(), frozenset(), frozenset()),
    # The pool call becomes an inline sequential loop (H3 owns concurrency).
    "capture/_survey_tensor.py": (
        frozenset({"_whole_tensor_score"}), frozenset(), frozenset()),
    # region_from_record rebuilt a holo record type (H2c owns that
    # direction); the additions are the DESIGN §5.3 typed output. The
    # hash-free identity law (2026-08-11) removed two of those additions —
    # ``region_id`` and its ``support_mask_sha256`` — because a region IS
    # its capture and its support grid (``capture.region_key``); the
    # carried ALGORITHM above the adaptation line is untouched.
    # The second block is C3's (RULINGS G4, 2026-08-22): the survey votes
    # a printed PITCH (``_snap_pitch`` over ``CANDIDATE_PITCHES_IN``)
    # where the source votes a count of 600-dpi engine dots (``_snap_c``
    # over ``PRINT_DPI``/``MAX_C_DOTS``).  ``PitchVote``/``PayloadSurvey``
    # change with the unit they carry, and the three functions with the
    # value they compare and median.  It is the same DECISION wherever
    # the source names a pitch holo2 also names — pinned on a seeded
    # sweep and on every candidate's tolerance shell in
    # ``test_oracle_survey.py`` — and a declared narrowing elsewhere.
    # C3b (RULINGS H1(b), 2026-08-22) adds ``candidate_pitches`` and
    # threads its result through the three functions: the candidate set
    # is per-SURVEY now — the blind set plus the DECLARED row's pitch —
    # because a stage that has been told the answer should not vote
    # ``None`` against it.  The source has no counterpart: its ladder
    # was "any whole number of dots", which has no outside.  So this is
    # an ADDITION on holo2's side, not a divergence inside a shared line.
    "capture/survey.py": (
        frozenset({"PitchVote", "PayloadSurvey", "_pitch_vote",
                   "_global_pitch", "survey_raster"}),
        frozenset({"region_from_record", "PRINT_DPI", "MAX_C_DOTS",
                   "_snap_c"}),
        frozenset({"support_mask_bytes", "RegionCandidate",
                   "region_candidates", "CANDIDATE_PITCHES_IN",
                   "_snap_pitch", "candidate_pitches"}),
    ),
}


def _strip_docstrings(node: ast.AST) -> ast.AST:
    for child in ast.walk(node):
        if isinstance(child, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)) and child.body:
            first = child.body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                child.body = child.body[1:] or [ast.Pass()]
    return node


def _definitions(path: Path) -> dict[str, str]:
    """Top-level defs/classes/assignments, docstring-free, as dumps."""
    tree = _strip_docstrings(ast.parse(path.read_text(encoding="utf-8")))
    out: dict[str, str] = {}
    for node in tree.body:  # type: ignore[attr-defined]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            out[node.name] = ast.dump(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = ast.dump(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out[node.target.id] = ast.dump(node)
    return out


@pytest.mark.parametrize("module", sorted(ADAPTATIONS))
def test_carry_differs_only_as_declared(module: str) -> None:
    changed, removed, added = ADAPTATIONS[module]
    original = _definitions(_HOLO / Path(module).name)
    carried = _definitions(_HOLO2 / module)

    assert set(original) - set(carried) == removed, module
    assert set(carried) - set(original) == added, module
    differing = {name for name in set(original) & set(carried)
                 if original[name] != carried[name]}
    assert differing == changed, (
        f"{module}: undeclared divergence from src/holo in {sorted(differing)}")


def test_declared_carries_exist() -> None:
    """Every H2a carry is present on both sides of the comparison.

    Scoped to H2a's own leaves: ``holo2`` also holds modules that merely
    share a name with something under ``holo/receive`` (``records.py`` is
    H1's, not a carry) and carries belonging to other phases, each of
    which pins itself in its own oracle.
    """
    for module in ADAPTATIONS:
        assert (_HOLO / Path(module).name).is_file(), module
        assert (_HOLO2 / module).is_file(), module


@pytest.mark.parametrize("module", sorted(ADAPTATIONS))
def test_carried_modules_import_nothing_from_holo(module: str) -> None:
    tree = ast.parse((_HOLO2 / module).read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    assert not (roots & {"holo", "paperholo", "experiments"}), module
