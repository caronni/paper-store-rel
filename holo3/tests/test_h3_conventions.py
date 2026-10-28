from __future__ import annotations

import ast
import collections
import hashlib
import importlib
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest

import holo3
from holo3.tests import _h3_sims, _h3_support
from holo3.tests import conftest as h3_conftest

WORKTREE_ROOT = _h3_support.WORKTREE_ROOT
TESTS_DIR = _h3_support.TESTS_DIR

EXTRA_PYTEST_ROOTS = ("holo2/measure/verdicts", "holo3/tests")
STANDALONE_PYTEST_FILES = ("conftest.py",)

ALLOWED_FILENAMES = ("__init__.py", "conftest.py")
TEST_PREFIX = "test_h3_"
SUPPORT_PREFIX = "_h3_"

# measured 2026-08-29 over tests + holo2/tests + holo2/measure/verdicts
# + holo3/tests + the repo-root conftest: exactly two collisions
ALLOWED_DUPLICATE_IMPORT_NAMES: dict[str, tuple[str, ...]] = {
    "conftest": (
        "conftest.py",
        "holo2/tests/conftest.py",
        "holo2/measure/verdicts/conftest.py"),
    "test_roundtrip": (
        "holo2/measure/verdicts/test_roundtrip.py",
        "tests/holo/test_roundtrip.py"),
}

PUBLISHED_FIXTURES = (
    "sim_k", "sim_color", "sim_k_rot", "sim_color_rot", "sim_k_null",
    "sim_k_degraded", "decode_k_w1", "decode_k_w8", "decode_k_rot",
    "decode_color_w8", "decode_color_rot1", "decode_k_no_close",
    "decode_k_complete", "decode_k_null", "decode_k_degraded_w1",
    "sim_k_local_patch", "decode_k_local_patch_w1",
    "decode_k_local_patch_off_w1", "decode_k_local_patch_w8",
    "sim_color_local_patch", "decode_color_local_patch_w1",
    "decode_color_local_patch_off_w1", "decode_color_local_patch_w8")

CWD_DEPENDENT_ATTRIBUTES = ("getcwd", "chdir")
CWD_DEPENDENT_PATH_ARGUMENTS = (".", "")

COLLECT_ONLY_BUDGET_S = 2.0


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


def test_tests_directory_is_a_package_so_its_conftest_cannot_shadow_holo2():
    marker = TESTS_DIR / "__init__.py"
    assert marker.is_file()
    assert marker.read_bytes() == b""
    assert _import_name(TESTS_DIR / "conftest.py") == "holo3.tests.conftest"
    assert (_import_name(WORKTREE_ROOT / "holo2" / "tests" / "conftest.py")
            == "conftest")


def _follows_naming_rule(name: str) -> bool:
    if name in ALLOWED_FILENAMES:
        return True
    if name.startswith(TEST_PREFIX):
        return True
    return name.startswith(SUPPORT_PREFIX) and not name.startswith("test")


def test_every_file_in_this_directory_follows_the_h3_naming_rule():
    checks = _h3_support.Checks("holo3/tests naming")
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
        checks.equal(f"{name} still collides at the declared paths",
                     found, tuple(sorted(declared)))
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
    assert "holo3/tests" not in _testpaths()
    assert "holo3" not in _testpaths()


def test_import_bootstrap_resolves_holo3_under_this_worktree():
    assert Path(holo3.__file__).resolve().parent == WORKTREE_ROOT / "holo3"
    assert str(WORKTREE_ROOT) in sys.path or "" in sys.path


def test_v1_and_holo2_packages_import_from_their_pinned_source_trees():
    import holo
    import holo2

    assert (Path(holo.__file__).resolve().parent
            == WORKTREE_ROOT / "src" / "holo")
    assert (Path(holo2.__file__).resolve().parent
            == WORKTREE_ROOT / "holo2" / "src" / "holo2")


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


def test_lane_gate_names_are_pinned():
    _h3_support.assert_golden("slow-lane gate", _h3_support.SLOW_LANE_ENV,
                              "HOLO3_RUN_SLOW_TESTS")
    _h3_support.assert_golden("oracle-sweep gate",
                              _h3_support.ORACLE_SWEEPS_ENV,
                              "HOLO3_RUN_ORACLE_SWEEPS")
    _h3_support.assert_golden("fixture-cache gate",
                              _h3_support.FIXTURE_CACHE_ENV,
                              "HOLO3_FIXTURE_CACHE")
    _h3_support.assert_golden("v1 serial gate", h3_conftest.V1_WORKERS_ENV,
                              "HOLO_RECEIVE_WORKERS")


def test_wall_budget_tripwire_constants_are_pinned():
    # slow re-measured 2026-08-30 at ~128 s quiet after the mixed-DPI sim
    # pair joined the lane (was ~96 s against 100)
    _h3_support.assert_golden(
        "wall budgets", _h3_support.WALL_BUDGET_S,
        {_h3_support.LANE_FAST: 15.0, _h3_support.LANE_SLOW: 140.0})


@pytest.mark.parametrize(
    "lane,elapsed_s,fires",
    [(_h3_support.LANE_FAST, 9.0, False),
     (_h3_support.LANE_FAST, 15.0, False),
     (_h3_support.LANE_FAST, 15.1, True),
     (_h3_support.LANE_FAST, 25.0, True),
     (_h3_support.LANE_SLOW, 70.0, False),
     (_h3_support.LANE_SLOW, 140.0, False),
     (_h3_support.LANE_SLOW, 140.1, True),
     (_h3_support.LANE_SLOW, 180.0, True)])
def test_wall_tripwire_fires_only_above_the_budget(lane, elapsed_s, fires):
    message = _h3_support.wall_tripwire_message(elapsed_s, lane)
    assert (message is not None) is fires
    if fires:
        assert _h3_support.TRIPWIRE_ADVICE in message
        assert f"{lane} lane wall" in message


class _StubReporter:

    def __init__(self) -> None:
        self.lines: list[tuple[str, bool]] = []

    def write_line(self, text: str, red: bool = False) -> None:
        self.lines.append((text, bool(red)))


class _StubPluginManager:

    def __init__(self, reporter: object) -> None:
        self._reporter = reporter

    def get_plugin(self, name: str) -> object | None:
        return self._reporter if name == "terminalreporter" else None


class _StubConfig:

    def __init__(self, reporter: object) -> None:
        self.pluginmanager = _StubPluginManager(reporter)


class _StubSession:

    def __init__(self, reporter: object) -> None:
        self.config = _StubConfig(reporter)
        self.exitstatus = 0


def _finished_session(elapsed_s: float) -> tuple[_StubSession, _StubReporter]:
    reporter = _StubReporter()
    session = _StubSession(reporter)
    h3_conftest.pytest_sessionstart(session)
    session.config._holo3_started_at = time.monotonic() - elapsed_s
    h3_conftest.pytest_sessionfinish(session, 0)
    return session, reporter


def test_the_session_finish_hook_fails_the_run_when_the_lane_runs_long():
    over = _h3_support.wall_budget_s() + 30.0
    session, reporter = _finished_session(over)
    assert session.exitstatus == 1
    assert len(reporter.lines) == 1
    text, red = reporter.lines[0]
    assert red is True
    assert "holo3 wall tripwire" in text
    assert _h3_support.TRIPWIRE_ADVICE in text


def test_the_session_finish_hook_stays_silent_inside_the_budget():
    session, reporter = _finished_session(0.0)
    assert session.exitstatus == 0
    assert reporter.lines == []


def test_the_session_finish_hook_is_inert_without_a_recorded_start():
    reporter = _StubReporter()
    session = _StubSession(reporter)
    h3_conftest.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 0
    assert reporter.lines == []


def test_this_session_is_inside_its_lane_wall_budget(session_elapsed_s):
    lane = _h3_support.lane_name()
    message = _h3_support.wall_tripwire_message(session_elapsed_s(), lane)
    assert message is None, message


FIXTURE_MARKERS = ("_pytestfixturefunction", "_fixture_function_marker")


def _declared_fixtures(module: object) -> frozenset[str]:
    return frozenset(
        name for name in dir(module)
        if any(hasattr(getattr(module, name), marker)
               for marker in FIXTURE_MARKERS))


def test_conftest_publishes_the_fixture_name_contract():
    declared = _declared_fixtures(h3_conftest)
    checks = _h3_support.Checks("published fixture contract")
    for name in PUBLISHED_FIXTURES:
        checks.check(f"conftest declares fixture {name}",
                     name in declared,
                     "the fixture-name contract is published to every area "
                     "builder; a rename must be loud")
    checks.assert_clean()


CACHE_KEY_INPUTS = (
    ("SOURCE_DIGEST", "0" * 64),
    ("RENDER_CACHE_VERSION", 99),
    ("K_FORMAT_REF", "c3-k-r0550@8x8"),
    ("COLOR_FORMAT_REF", "c3-cmy8-r0550@11x11"),
    ("K_PAYLOAD_TAG", b"holo3-sim-k-moved"),
    ("COLOR_PAYLOAD_TAG", b"holo3-sim-color-moved"),
)


def test_render_cache_version_is_an_integer_a_human_bumps():
    assert isinstance(_h3_sims.RENDER_CACHE_VERSION, int)
    assert not isinstance(_h3_sims.RENDER_CACHE_VERSION, bool)
    assert _h3_sims.RENDER_CACHE_VERSION >= 1


def test_the_fixture_cache_key_is_hexadecimal_and_stable_within_a_tree():
    key = h3_conftest._cache_key()
    assert len(key) == 16
    assert set(key) <= set("0123456789abcdef")
    assert h3_conftest._cache_key() == key


@pytest.mark.parametrize("name,replacement", CACHE_KEY_INPUTS,
                         ids=[row[0] for row in CACHE_KEY_INPUTS])
def test_every_declared_input_moves_the_fixture_cache_key(
        name, replacement, monkeypatch):
    before = h3_conftest._cache_key()
    assert getattr(_h3_sims, name) != replacement
    monkeypatch.setattr(_h3_sims, name, replacement)
    assert h3_conftest._cache_key() != before, (
        f"{name} does not reach the fixture cache key: a stale cached sim "
        f"would survive a change to it")


def test_the_source_digest_is_the_hash_of_the_sim_builder_module():
    source = (TESTS_DIR / "_h3_sims.py").read_bytes()
    _h3_support.assert_golden("_h3_sims SOURCE_DIGEST",
                              _h3_sims.SOURCE_DIGEST,
                              hashlib.sha256(source).hexdigest())


DRIFT_MODULE_GLOB = "test_h3_drift_*.py"
N_DRIFT_MODULES = 4


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
    assert sum(len(row) for row in targets.values()) > 40
    for name, row in sorted(targets.items()):
        assert row, name
        assert all(module.split(".")[0] in ("holo", "holo2")
                   for module in row), name


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


def test_the_import_probe_still_notices_a_module_that_is_not_there():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("holo.module_that_never_existed")


def test_collection_opens_no_capture():
    _h3_support.skip_unless_slow_lane("the subprocess collection probe")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "holo3/tests", "--collect-only",
         "-q"], cwd=WORKTREE_ROOT, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = [line for line in completed.stdout.splitlines() if line.strip()]
    match = re.fullmatch(r"\d+ tests collected in ([0-9.]+)s", summary[-1])
    assert match, summary[-1]
    assert float(match.group(1)) < COLLECT_ONLY_BUDGET_S, (
        f"pytest's own collection clock read {match.group(1)}s: collection "
        f"must import no capture and generate no sim")
