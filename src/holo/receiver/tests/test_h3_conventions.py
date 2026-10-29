from __future__ import annotations

import ast
import collections
import dataclasses
import hashlib
import importlib
import inspect
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import holo.receiver
from holo.receiver.tests import _h3_fixture_build, _h3_sims, _h3_sims_cmy
from holo.receiver.tests import _h3_sims_field, _h3_sims_p_axis, _h3_support
from holo.receiver.tests import conftest as h3_conftest

WORKTREE_ROOT = _h3_support.WORKTREE_ROOT
TESTS_DIR = _h3_support.TESTS_DIR

# "tests" added 2026-09-06: testpaths dropped the paperholo root (explicit
# lane now, Germano's ruling), so the whole-tree uniqueness law below only
# still covers it because this tuple names it directly.
EXTRA_PYTEST_ROOTS = ("src/holo/receiver/tests", "tests")
STANDALONE_PYTEST_FILES = ("conftest.py",)

ALLOWED_FILENAMES = ("__init__.py", "conftest.py")
TEST_PREFIX = "test_h3_"
SUPPORT_PREFIX = "_h3_"

# re-measured 2026-09-06 over pyproject's testpaths + EXTRA_PYTEST_ROOTS (now
# src/holo/receiver/tests and tests, the latter re-added when testpaths
# dropped the paperholo root) + the repo-root conftest: no collision is
# left.  The table is self-retiring (a declared row whose paths no longer
# collide fails the test below), so it is empty until a reviewed row is
# needed again; an undeclared collision fails.
ALLOWED_DUPLICATE_IMPORT_NAMES: dict[str, tuple[str, ...]] = {}

CWD_DEPENDENT_ATTRIBUTES = ("getcwd", "chdir")
CWD_DEPENDENT_PATH_ARGUMENTS = (".", "")

def _testpaths() -> tuple[str, ...]:
    config = tomllib.loads((WORKTREE_ROOT / "pyproject.toml").read_text())
    ini = config["tool"]["pytest"]["ini_options"]
    return tuple(ini["testpaths"])


def _pytest_roots() -> tuple[Path, ...]:
    return tuple(WORKTREE_ROOT / name
                 for name in _testpaths() + EXTRA_PYTEST_ROOTS)


def _import_name(path: Path) -> str:
    parts = [path.stem]
    directory = path.parent
    while (directory / "__init__.py").exists():
        parts.append(directory.name)
        directory = directory.parent
    return ".".join(reversed(parts))


def _scanned_files() -> tuple[Path, ...]:
    found: list[Path] = [WORKTREE_ROOT / name
                         for name in STANDALONE_PYTEST_FILES]
    for root in _pytest_roots():
        found.extend(_h3_support.source_files(root))
    return tuple(sorted(set(found)))


def _import_name_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = collections.defaultdict(list)
    for path in _scanned_files():
        index[_import_name(path)].append(
            str(path.relative_to(WORKTREE_ROOT)))
    return index


def _tracked_python_files() -> tuple[str, ...]:
    listing = subprocess.run(
        ["git", "ls-files", "-z", "*.py"], cwd=WORKTREE_ROOT,
        check=True, capture_output=True, text=True).stdout
    return tuple(row for row in listing.split("\0") if row)


def test_tests_directory_is_a_package_so_its_conftest_cannot_shadow_the_root():
    marker = TESTS_DIR / "__init__.py"
    assert marker.is_file()
    assert marker.read_bytes() == b""
    assert _import_name(TESTS_DIR / "conftest.py") == "holo.receiver.tests.conftest"
    assert _import_name(WORKTREE_ROOT / "conftest.py") == "conftest"


def _follows_naming_rule(name: str) -> bool:
    if name in ALLOWED_FILENAMES:
        return True
    if name.startswith(TEST_PREFIX):
        return True
    return name.startswith(SUPPORT_PREFIX) and not name.startswith("test")


def test_every_file_in_this_directory_follows_the_h3_naming_rule():
    checks = _h3_support.Checks("src/holo/receiver/tests naming")
    for path in _h3_support.source_files(TESTS_DIR):
        checks.check(
            f"{path.name} is test_h3_*.py, _h3_*.py, conftest.py "
            f"or __init__.py",
            _follows_naming_rule(path.name),
            "the h3 prefix is what makes the basename globally unique")
    checks.assert_clean()


@pytest.mark.parametrize(
    "name,accepted",
    [("test_h3_lib_bch.py", True), ("_h3_sims.py", True),
     ("conftest.py", True), ("__init__.py", True),
     ("test_bch.py", False), ("test_lib_bch.py", False),
     ("helpers.py", False), ("test_h3.py", False)])
def test_the_naming_rule_rejects_unprefixed_module_names(name, accepted):
    assert _follows_naming_rule(name) is accepted


def test_pytest_import_names_are_unique_across_every_collected_root():
    index = _import_name_index()
    checks = _h3_support.Checks("repo-wide import-name uniqueness")
    for name, paths in sorted(index.items()):
        if len(paths) < 2:
            continue
        checks.check(
            f"{name} collides across {sorted(paths)}",
            name in ALLOWED_DUPLICATE_IMPORT_NAMES,
            "prepend import mode imports by this name: rename the module "
            "or add a reviewed row to ALLOWED_DUPLICATE_IMPORT_NAMES")
    checks.assert_clean()


def test_declared_duplicate_import_names_still_collide():
    index = _import_name_index()
    checks = _h3_support.Checks("allowed-duplicate table is self-retiring")
    for name, declared in sorted(ALLOWED_DUPLICATE_IMPORT_NAMES.items()):
        found = tuple(sorted(index.get(name, ())))
        present = tuple(sorted(row for row in declared
                               if (WORKTREE_ROOT / row).exists()))
        checks.check(f"{name} is declared by at least one live path",
                     bool(present), f"declared {sorted(declared)}")
        checks.equal(f"{name} collides at exactly the live declared paths",
                     found, present)
    checks.assert_clean()


def _tracked_here(rows: tuple[str, ...]) -> set[str]:
    return {Path(row).name for row in rows
            if (WORKTREE_ROOT / row).parent == TESTS_DIR
            and Path(row).name not in ALLOWED_FILENAMES}


# the suite is committed since 28cf0c2, so its own basenames are tracked
# once; the surviving contract is that nothing ELSE in the repo carries them
def test_holo3_test_basenames_are_unique_against_every_tracked_repo_file():
    rows = _tracked_python_files()
    tracked = collections.Counter(Path(row).name for row in rows)
    here = _tracked_here(rows)
    checks = _h3_support.Checks("h3 prefix guarantees repo-wide uniqueness")
    for path in _h3_support.source_files(TESTS_DIR):
        if path.name in ALLOWED_FILENAMES:
            continue
        checks.equal(
            f"{path.name} is carried by this directory alone",
            tracked[path.name], 1 if path.name in here else 0)
    assert here, "the committed suite must be tracked for this gate to bite"
    for name in sorted(here):
        checks.equal(f"{name} is tracked exactly once repo-wide",
                     tracked[name], 1)
    checks.assert_clean()


def test_holo3_tests_is_not_in_pyproject_testpaths():
    assert "src/holo/receiver/tests" not in _testpaths()
    assert not any("receiver" in root for root in _testpaths())


def test_both_packages_import_from_this_worktrees_source_tree():
    # `import holo.receiver` at the head of this module binds both names.
    # Since the 2026-09-05 move the receiver is `holo.receiver` under src/,
    # found the way every other holo.* module is: `src/` on the path.
    assert (Path(holo.receiver.__file__).resolve().parent
            == WORKTREE_ROOT / "src" / "holo" / "receiver")
    assert str(WORKTREE_ROOT / "src") in sys.path
    # Since the v1 receiver was retired 2026-09-05, `holo` is no longer a
    # second receiver but the format authority: the generator that prints
    # sheets and the format law the drift lanes compare against.  The pin
    # therefore matters more, not less — a `holo` resolved from anywhere
    # but this worktree's src/ would silently move the oracle.
    assert (Path(holo.__file__).resolve().parent
            == WORKTREE_ROOT / "src" / "holo")


def _cwd_dependent_nodes(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute)
                and node.attr in CWD_DEPENDENT_ATTRIBUTES):
            found.append(f"line {node.lineno}: .{node.attr}()")
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = callee.attr if isinstance(callee, ast.Attribute) else (
            callee.id if isinstance(callee, ast.Name) else "")
        if name != "Path" or len(node.args) != 1:
            continue
        argument = node.args[0]
        if (isinstance(argument, ast.Constant)
                and argument.value in CWD_DEPENDENT_PATH_ARGUMENTS):
            found.append(f"line {node.lineno}: Path({argument.value!r})")
    return tuple(found)


def test_no_test_module_depends_on_the_working_directory():
    checks = _h3_support.Checks("cwd independence")
    for path in _h3_support.source_files(TESTS_DIR):
        checks.equal(f"{path.name} names no cwd-relative anchor",
                     _cwd_dependent_nodes(path), ())
    checks.assert_clean()


def test_the_cwd_gate_still_detects_a_planted_landmine(tmp_path):
    landmine = tmp_path / "landmine.py"
    landmine.write_text(
        "import os\nfrom pathlib import Path\n"
        "HERE = Path(os.getcwd())\nALSO = Path('.')\n")
    found = _cwd_dependent_nodes(landmine)
    assert len(found) == 2, found


FIXTURE_MARKERS = ("_pytestfixturefunction", "_fixture_function_marker")


def _fixture_marker(function: object) -> object | None:
    for marker in FIXTURE_MARKERS:
        if hasattr(function, marker):
            return getattr(function, marker)
    return None


def _declared_fixtures(module: object) -> frozenset[str]:
    return frozenset(
        name for name in dir(module)
        if _fixture_marker(getattr(module, name)) is not None)


#: The published fixture contract, DERIVED rather than hand-copied: every
#: function the conftest binds as a fixture, the page-field seven it
#: imports from `_h3_fixtures_field` included (an imported fixture
#: function IS a fixture of the importing conftest).
PUBLISHED_FIXTURES = _declared_fixtures(h3_conftest)


def _requesting_names() -> frozenset[str]:
    found: set[str] = set()
    for path in sorted(TESTS_DIR.glob(f"{TEST_PREFIX}*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            fixture = any("fixture" in ast.dump(decorator)
                          for decorator in node.decorator_list)
            if not (node.name.startswith("test_") or fixture):
                continue
            found |= {argument.arg for argument in node.args.args}
    return frozenset(found)


def _reached_fixtures() -> frozenset[str]:
    """Every published fixture some test module really asks for.

    A fixture is reached when a test (or a module's own fixture) names it,
    or when a reached fixture depends on it, or when it is autouse — the
    three ways pytest itself can arrive at one.
    """
    autouse = {name for name in PUBLISHED_FIXTURES
               if getattr(_fixture_marker(getattr(h3_conftest, name)),
                          "autouse", False)}
    pending = list((_requesting_names() | autouse) & PUBLISHED_FIXTURES)
    reached: set[str] = set()
    while pending:
        name = pending.pop()
        if name in reached:
            continue
        reached.add(name)
        parameters = inspect.signature(getattr(h3_conftest, name)).parameters
        pending.extend(set(parameters) & PUBLISHED_FIXTURES)
    return frozenset(reached)


def test_every_published_fixture_is_asked_for_by_some_test_module():
    # A rename is silent in the fast lane, because every decode fixture is
    # slow-gated: the module that used to ask for it simply gets nothing
    # and skips.  What this catches instead is the residue — a fixture
    # (and the render or decode behind it) no test reaches at all.
    checks = _h3_support.Checks("published fixture contract")
    assert PUBLISHED_FIXTURES, "the conftest publishes no fixture at all"
    reached = _reached_fixtures()
    for name in sorted(PUBLISHED_FIXTURES):
        checks.check(f"some test module requests fixture {name}",
                     name in reached,
                     "no test reaches this fixture: delete it, or the "
                     "test that should have asked for it went missing")
    checks.assert_clean()


#: (module, name, replacement).  ALL FOUR stimulus modules carry a
#: SOURCE_DIGEST: the W6 split moved the displaced page and the confetti
#: platen into `_h3_sims_field`, the 2026-09-16 split moved the two p300
#: volumes into `_h3_sims_p_axis`, the cmy pages live in `_h3_sims_cmy`
#: (2026-10-12), and a key that hashed only the half they left would
#: serve stale renders of them.
CACHE_KEY_INPUTS = (
    (_h3_sims, "SOURCE_DIGEST", "0" * 64),
    (_h3_sims_field, "SOURCE_DIGEST", "0" * 64),
    (_h3_sims_p_axis, "SOURCE_DIGEST", "0" * 64),
    (_h3_sims_cmy, "SOURCE_DIGEST", "0" * 64),
    (_h3_sims_cmy, "CMY_FORMAT_REF", "c3-cmy-r0775@10x10"),
    (_h3_sims_cmy, "CMY_PAYLOAD_TAG", b"holo3-sim-cmy-moved"),
    (_h3_sims_cmy, "CMY_C2_FORMAT_REF", "c2-cmy-r0700@10x10"),
    (_h3_sims_cmy, "CMY_C2_PAYLOAD_TAG", b"holo3-sim-cmy-c2-moved"),
    (_h3_sims_p_axis, "P_AXIS_FORMAT_REF", "c2-cmy8-r0550-p301@10x10"),
    (_h3_sims_p_axis, "P_AXIS_PAYLOAD_TAG", b"holo3-sim-p-axis-moved"),
    (_h3_sims_p_axis, "P_AXIS_K_FORMAT_REF", "c3-k-r0550-p301@10x10"),
    (_h3_sims_p_axis, "P_AXIS_K_PAYLOAD_TAG", b"holo3-sim-p-axis-k-moved"),
    (_h3_sims, "RENDER_CACHE_VERSION", 99),
    (_h3_sims, "K_FORMAT_REF", "c3-k-r0550@8x8"),
    (_h3_sims, "COLOR_FORMAT_REF", "c3-cmy8-r0550@11x11"),
    (_h3_sims, "K_PAYLOAD_TAG", b"holo3-sim-k-moved"),
    (_h3_sims, "COLOR_PAYLOAD_TAG", b"holo3-sim-color-moved"),
)


@pytest.mark.parametrize("module,name,replacement", CACHE_KEY_INPUTS,
                         ids=[f"{row[0].__name__.rsplit('.', 1)[-1]}."
                              f"{row[1]}" for row in CACHE_KEY_INPUTS])
def test_every_declared_input_moves_the_fixture_cache_key(
        module, name, replacement, monkeypatch):
    before = _h3_fixture_build._cache_key()
    assert _h3_fixture_build._cache_key() == before, (
        "the key is not stable within one tree: every row below would "
        "then read as a move")
    assert getattr(module, name) != replacement
    monkeypatch.setattr(module, name, replacement)
    assert _h3_fixture_build._cache_key() != before, (
        f"{module.__name__}.{name} does not reach the fixture cache key: a "
        f"stale cached sim would survive a change to it")


#: The DECODE key's module-level inputs (2026-09-20).  The stimulus key
#: is one of them, so every row above reaches this key too; the source
#: rows are the production tree, and the row below moves ONE file's
#: digest rather than the file, which is the same thing the cache sees.
_MOVED_SOURCE_ROWS = (("receiver/moved.py", "0" * 64),
                      *_h3_fixture_build.HOLO_SOURCE_ROWS[1:])
DECODE_KEY_INPUTS = (
    (_h3_fixture_build, "_cache_key", lambda: "0" * 16),
    (_h3_fixture_build, "HOLO_SOURCE_ROWS", _MOVED_SOURCE_ROWS),
    (_h3_fixture_build, "DECODE_CACHE_VERSION", 99),
    (_h3_fixture_build, "_ENV_TAG", "moved"),
)

#: (label, captures, workers, extra_argv, drop_rows, cache_tag,
#: keep_planes, traced) and one moved value for each: the decode's OWN
#: inputs, which the key takes by argument.
_DECODE_CAPTURE = _h3_sims.SimCapture(
    name="key-probe", format_ref=_h3_sims.K_FORMAT_REF, dpi=1200.0, rot_k=0,
    tiff=TESTS_DIR / "no-such.tiff", tiff_sha256="a" * 64,
    payload=TESTS_DIR / "no-such.bin", payload_sha256="b" * 64,
    payload_bytes=6000, emit_dir=None)
_DECODE_CALL = ("probe", (_DECODE_CAPTURE,), 1, ("--max-pages", "1"), (),
                "", False, False)
DECODE_CALL_INPUTS = (
    ("label", "probe-moved"),
    ("captures",
     (dataclasses.replace(_DECODE_CAPTURE, tiff_sha256="c" * 64),)),
    ("workers", 8),
    ("extra_argv", ("--complete", "--max-pages", "1")),
    ("drop_rows", ("tiles.local",)),
    ("cache_tag", "a-patch-this-fixture-applies"),
    ("keep_planes", True),
    ("traced", True),
)


@pytest.mark.parametrize("module,name,replacement", DECODE_KEY_INPUTS,
                         ids=[row[1] for row in DECODE_KEY_INPUTS])
def test_every_declared_input_moves_the_decode_cache_key(
        module, name, replacement, monkeypatch):
    before = _h3_fixture_build._decode_key(*_DECODE_CALL)
    assert _h3_fixture_build._decode_key(*_DECODE_CALL) == before
    assert getattr(module, name) != replacement
    monkeypatch.setattr(module, name, replacement)
    assert _h3_fixture_build._decode_key(*_DECODE_CALL) != before, (
        f"{module.__name__}.{name} does not reach the decode cache key: a "
        f"stale cached decode would survive a change to it")


@pytest.mark.parametrize("position,replacement", DECODE_CALL_INPUTS,
                         ids=[row[0] for row in DECODE_CALL_INPUTS])
def test_every_input_of_the_decode_itself_moves_the_decode_cache_key(
        position, replacement):
    names = ("label", "captures", "workers", "extra_argv", "drop_rows",
             "cache_tag", "keep_planes", "traced")
    before = _h3_fixture_build._decode_key(*_DECODE_CALL)
    moved = list(_DECODE_CALL)
    moved[names.index(position)] = replacement
    assert _h3_fixture_build._decode_key(*moved) != before, (
        f"the decode's {position} does not reach the decode cache key")


# ------------------------- what a decode record publishes (2026-10-18, R3)

#: A run dir as the receiver leaves it: the flat products, `sched-trace/`,
#: and intake's per-capture plane scratch at `run_dir / capture_id[:12]`
#: (plugins/intake.py).  The scratch is 65 MB of a colour capture's record
#: and no receiver test opens it; the analyzer's S-tier record does, and
#: asks for it by name (`keep_planes`).
_PUBLISH_PRODUCTS = ("argv", "report.json", "events.jsonl", "facts.npz",
                     "tree", "pane-page-0.png")


def _fake_decode(run_dir: Path, capture: _h3_sims.SimCapture,
                 extra_dirs: tuple[str, ...] = (), with_trace: bool = True
                 ) -> _h3_fixture_build.DecodeRecord:
    run_dir.mkdir(parents=True)
    for name in _PUBLISH_PRODUCTS:
        (run_dir / name).write_text(name)
    if with_trace:
        trace = run_dir / "sched-trace"
        trace.mkdir()
        (trace / "summary.json").write_text("{}")
    scratch = run_dir / capture.tiff_sha256[:12]
    scratch.mkdir()
    (scratch / "l00-grey.npy").write_bytes(b"plane")
    for name in extra_dirs:
        (run_dir / name).mkdir()
        (run_dir / name / "x").write_text("x")
    return _h3_fixture_build.DecodeRecord(
        label="publish-probe", format_ref=capture.format_ref, rot_k=0,
        workers=1, argv=(), exit_code=0, status="verified", payload=b"p",
        payload_sha256=None, certified=0, certificates={},
        certificate_signature=(), events=(),
        report={"capture_facts": [{"capture": capture.tiff_sha256}]},
        run_dir=run_dir, out_path=run_dir.parent / "payload.bin",
        out_exists=False, stdout="", stderr="", wall_s=0.0)


def _publish_and_reload(tmp_path: Path, monkeypatch, label: str,
                        extra_dirs: tuple[str, ...] = (),
                        with_trace: bool = True,
                        **kwargs) -> Path:
    monkeypatch.setenv(_h3_support.FIXTURE_CACHE_ENV, str(tmp_path / "cache"))
    capture = dataclasses.replace(_DECODE_CAPTURE, tiff_sha256="d" * 64)
    monkeypatch.setattr(
        _h3_fixture_build, "_run_decode",
        lambda label, captures, root, *rest: _fake_decode(
            root / label / "run", capture, extra_dirs, with_trace))
    _h3_fixture_build.cached_decode(label, (capture,), tmp_path / "miss",
                                    workers=1, **kwargs)
    hit = _h3_fixture_build.cached_decode(label, (capture,),
                                          tmp_path / "hit", workers=1,
                                          **kwargs)
    assert (tmp_path / "cache") in hit.run_dir.parents, (
        "the second call did not read the record back from the cache")
    return hit.run_dir


def test_the_decode_cache_publishes_products_not_the_plane_scratch(
        tmp_path, monkeypatch):
    run_dir = _publish_and_reload(tmp_path, monkeypatch, "publish-products",
                                  traced=True)
    for name in _PUBLISH_PRODUCTS:
        assert (run_dir / name).read_text() == name, name
    assert (run_dir / "sched-trace" / "summary.json").is_file()
    assert sorted(path.name for path in run_dir.iterdir()
                  if path.is_dir()) == ["sched-trace"], (
        "the cached record carries the per-capture plane scratch")


def test_a_record_that_asks_for_its_planes_keeps_them(tmp_path,
                                                      monkeypatch):
    run_dir = _publish_and_reload(tmp_path, monkeypatch, "publish-planes",
                                  keep_planes=True, traced=True)
    assert (run_dir / ("d" * 12) / "l00-grey.npy").read_bytes() == b"plane"
    assert (run_dir / "sched-trace" / "summary.json").is_file()


def test_an_unnamed_run_dir_directory_is_refused_at_publication(
        tmp_path, monkeypatch):
    # Neither a declared product nor a capture's scratch: dropping it
    # silently is the 39d4ebba bug (a product the warm lane then misses),
    # and copying it silently is D4's.  It must be named first.
    with pytest.raises(RuntimeError, match="mystery"):
        _publish_and_reload(tmp_path, monkeypatch, "publish-unnamed",
                            extra_dirs=("mystery",), traced=True)


# ------------------- a traced record under an untraced key (2026-10-18, R4)
#
# Review 2026-10-17 D10: the trace pin's OFF arm never cleared
# HOLO3_SCHED_TRACE and the decode key did not carry it, so with the
# variable exported a TRACED decode was published under the OFF key and
# the OFF-vs-ON byte identity compared a traced run with itself.  The run
# dir is the ground truth: `sched-trace/` is there iff the run was traced,
# and a key publishes only the kind of record it declares (`traced`).


def test_a_traced_run_dir_is_refused_under_an_untraced_key(tmp_path,
                                                           monkeypatch):
    with pytest.raises(RuntimeError, match="sched-trace"):
        _publish_and_reload(tmp_path, monkeypatch, "publish-stray-trace")
    assert not list((tmp_path / "cache").rglob("record.pkl")), (
        "a traced record was published under an untraced key")


def test_an_untraced_run_dir_is_refused_under_a_traced_key(tmp_path,
                                                           monkeypatch):
    with pytest.raises(RuntimeError, match="sched-trace"):
        _publish_and_reload(tmp_path, monkeypatch, "publish-missing-trace",
                            with_trace=False, traced=True)
    assert not list((tmp_path / "cache").rglob("record.pkl")), (
        "an untraced record was published under a traced key")


def test_an_untraced_run_publishes_under_the_default_key(tmp_path,
                                                         monkeypatch):
    run_dir = _publish_and_reload(tmp_path, monkeypatch, "publish-untraced",
                                  with_trace=False)
    for name in _PUBLISH_PRODUCTS:
        assert (run_dir / name).read_text() == name, name
    assert not (run_dir / "sched-trace").exists()


def test_a_decode_fixture_that_patches_production_declares_a_cache_tag():
    """The decode key reads the tree and the stimulus; it cannot see a
    monkeypatch a fixture applies AROUND its decode, so such a fixture
    must name the patch in `cache_tag` or a stale record is served
    silently on the next run."""
    source = (Path(h3_conftest.__file__)).read_text()
    tree = ast.parse(source)
    patch_marks = ("monkeypatch", "mock.patch", "patch.object", "setattr(")
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not any("fixture" in ast.unparse(d) for d in node.decorator_list):
            continue
        body = ast.get_source_segment(source, node) or ""
        if "_decode_once(" not in body and "_decode_group(" not in body:
            continue
        if any(mark in body for mark in patch_marks) and "cache_tag=" not in body:
            offenders.append(node.name)
    assert not offenders, (
        f"{offenders}: a decode fixture patches production without a "
        f"cache_tag naming the patch")


def test_the_source_rows_cover_every_production_module():
    """The digest's reach, not its value: the row table IS the tree.

    Whatever the cache is keyed on has to be every `.py` under
    `src/holo` that is not this test package, or a production edit could
    land behind a decode the cache still serves.
    """
    root = _h3_fixture_build._PRODUCTION_ROOT
    found = {str(path.relative_to(root))
             for path in _h3_support.source_files(root)
             if TESTS_DIR not in path.parents}
    assert found, "no production module reached the decode cache key"
    assert {name for name, _sha in _h3_fixture_build.HOLO_SOURCE_ROWS} == found
    assert not any(name.startswith("receiver/tests/")
                   for name, _sha in _h3_fixture_build.HOLO_SOURCE_ROWS)


@pytest.mark.parametrize("module",
                         (_h3_sims, _h3_sims_cmy, _h3_sims_field,
                          _h3_sims_p_axis),
                         ids=lambda module: module.__name__.rsplit(".", 1)[-1])
def test_the_source_digest_is_the_hash_of_its_own_sim_builder_module(module):
    name = module.__name__.rsplit(".", 1)[-1]
    source = (TESTS_DIR / f"{name}.py").read_bytes()
    _h3_support.assert_golden(f"{name} SOURCE_DIGEST", module.SOURCE_DIGEST,
                              hashlib.sha256(source).hexdigest())


DRIFT_MODULE_GLOB = "test_h3_drift_*.py"
#: test_h3_drift_receiver.py went with the v1 receiver 2026-09-05
#: (`src/holo/receive` deleted at 284ae3e): fifteen of its declared targets
#: were `holo.receive.*` and only its two surviving format/gen legs were
#: worth keeping, so they folded into test_h3_drift_format.py.
N_DRIFT_MODULES = 3
#: 45 declared targets after the suite-preparation package, minus the five
#: `holo.receive.*` ones in kernels (8 -> 3), minus the receiver module's
#: eighteen (sixteen declared at import, two lazily inside the A3/A4b
#: tests), plus the one that moved with the folded printed-cells test
#: (holo.gen.compose, so format 15 -> 16) = 23.  A floor, not a ceiling.
N_DRIFT_TARGETS_FLOOR = 23


def _importorskip_targets() -> dict[str, tuple[str, ...]]:
    found: dict[str, set[str]] = {}
    for path in sorted(TESTS_DIR.glob(DRIFT_MODULE_GLOB)):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "importorskip"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)):
                found.setdefault(path.name, set()).add(node.args[0].value)
    return {name: tuple(sorted(targets))
            for name, targets in sorted(found.items())}


def test_every_drift_module_guards_its_cross_tree_imports():
    targets = _importorskip_targets()
    assert len(targets) == N_DRIFT_MODULES, sorted(targets)
    assert sum(len(row) for row in targets.values()) >= N_DRIFT_TARGETS_FLOOR
    for name, row in sorted(targets.items()):
        assert row, name
        assert all(module.split(".")[0] == "holo" for module in row), name


def test_no_drift_module_silently_skips_its_whole_corpus():
    _h3_support.skip_unless_slow_lane("the cross-tree import probe")
    checks = _h3_support.Checks("drift corpora are running, not skipping")
    for name, row in sorted(_importorskip_targets().items()):
        for module in row:
            try:
                importlib.import_module(module)
            except Exception as exc:
                checks.check(f"{name} imports {module}", False, repr(exc))
                continue
            checks.check(f"{name} imports {module}", True)
    checks.assert_clean()


def test_collection_opens_no_capture(tmp_path):
    _h3_support.skip_unless_slow_lane("the subprocess collection probe")
    # A cold fixture cache and a fresh basetemp of its own: whatever a
    # collection-time render or decode produced would have to land in one
    # of them, and both are this test's to inspect afterwards.
    cache = tmp_path / "fixture-cache"
    cache.mkdir()
    basetemp = tmp_path / "basetemp"
    environment = dict(os.environ)
    environment[_h3_support.FIXTURE_CACHE_ENV] = str(cache)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "src/holo/receiver/tests",
         "--collect-only", "-q", "-p", "no:cacheprovider",
         "--basetemp", str(basetemp)],
        cwd=WORKTREE_ROOT, capture_output=True, text=True, env=environment)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = [line for line in completed.stdout.splitlines() if line.strip()]
    assert re.fullmatch(r"\d+ tests collected in [0-9.]+s", summary[-1]), (
        summary[-1])
    assert sorted(cache.rglob("*")) == [], (
        "collection wrote into the fixture cache: it must import no "
        "capture and generate no sim")
    assert not basetemp.exists() or sorted(basetemp.rglob("*")) == [], (
        "collection wrote into pytest's own tmp tree: a sim root was "
        "materialised while nothing was being run")


# ------------------------------------- golden vs measured (2026-10-03, S10)

#: Where `assert_golden` may be called, and how often: the PRINTED-FORMAT
#: pins -- keystream, site geometry, BCH / LDPC tables, fountain block
#: law, format identities and fossil seeds, the frozen stimulus renders
#: and the recovered payload's sha (= the emission's).  Everything else
#: a test pins about the receiver -- prices, key vocabularies, fact field
#: tuples, event unions, fold write maps, stage names, floors, decoder
#: outputs -- is `assert_measured`, which moves with a dated ledger line;
#: 114 such calls were reclassified on 2026-10-03 (S10) after receiver
#: changes had edited values a "never update" helper was holding.  A new
#: golden call site is a reviewed row here, never a drive-by.
GOLDEN_CALL_SITES: dict[str, int] = {
    "test_h3_conventions.py": 1,
    "test_h3_drift_declared.py": 4,
    "test_h3_drift_kernels.py": 4,
    "test_h3_e2e_cmy.py": 1,
    "test_h3_e2e_cmy_c2.py": 1,
    "test_h3_e2e_column_groups.py": 1,
    "test_h3_e2e_field_frame.py": 5,
    "test_h3_e2e_modes.py": 2,
    "test_h3_e2e_p_axis.py": 2,
    "test_h3_e2e_rotations.py": 6,
    "test_h3_e2e_sims.py": 2,
    "test_h3_field_estimator.py": 1,
    "test_h3_format_fountain.py": 1,
    "test_h3_format_identity.py": 6,
    "test_h3_format_keystream.py": 8,
    "test_h3_format_metadata.py": 1,
    "test_h3_format_pilots.py": 6,
    "test_h3_format_tile_codec.py": 1,
    "test_h3_lib_bch.py": 4,
    "test_h3_lib_geometry.py": 2,
    "test_h3_lib_ldpc.py": 2,
    "test_h3_multires.py": 3,
    "test_h3_survey_pitch_fallback.py": 1,
}


def _helper_calls(name: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for path in sorted(TESTS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        count = sum(1 for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, (ast.Attribute, ast.Name))
                    and getattr(node.func, "attr",
                                getattr(node.func, "id", None)) == name)
        if count:
            found[path.name] = count
    return found


def test_assert_golden_is_called_only_at_the_printed_format_sites():
    found = _helper_calls("assert_golden")
    found.pop("_h3_support.py", None)
    assert found == GOLDEN_CALL_SITES, (
        "assert_golden is for printed-format values only; a receiver-axis "
        "pin is assert_measured with a dated ledger line")


def test_every_module_with_a_measured_pin_keeps_a_dated_ledger():
    """`assert_measured` says "re-pin only with the cause named in the
    module's dated ledger", so the module has to have one."""
    undated = sorted(
        name for name in _helper_calls("assert_measured")
        if name != "_h3_support.py"
        and not re.search(r"20\d\d-\d\d-\d\d", (TESTS_DIR / name).read_text()))
    assert undated == []
