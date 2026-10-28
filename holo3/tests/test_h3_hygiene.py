from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

from pyflakes import messages as pyflakes_messages
from pyflakes.api import checkPath

from holo3.tests import _h3_support

WORKTREE_ROOT = _h3_support.WORKTREE_ROOT
HOLO3_ROOT = _h3_support.HOLO3_ROOT
TESTS_DIR = _h3_support.TESTS_DIR
MEASURE_ROOT = WORKTREE_ROOT / "measure"

FOREIGN_TREES = ("holo", "holo2", "paperholo", "experiments", "_distill")

EXCLUDED_DIRS = ("__pycache__", "conversion_docs")
PRODUCTION_EXCLUDED_DIRS = ("__pycache__", "conversion_docs", "tests")

FIREWALL_ALLOWLIST: dict[str, str] = {
    "_h3_sims.py": "builds the sim captures with the src/holo generator",
    "conftest.py": "wires the sim fixtures that _h3_sims produces",
    "test_h3_conventions.py": "pins where holo and holo2 import from",
    "test_h3_drift_kernels.py": "cross-tree kernel equivalence",
    "test_h3_drift_format.py": "cross-tree printed-format equivalence",
    "test_h3_drift_receiver.py": "cross-tree receiver numerics",
    "test_h3_drift_declared.py": "the declared-divergence table",
    "test_h3_page_domain.py": "builds the 3-page sims with the src/holo generator",
}

WALL_CLOCK_NAMES = ("perf_counter", "monotonic", "time_ns",
                    "perf_counter_ns", "monotonic_ns", "now", "utcnow")
METER_NAMES = ("thread_time", "process_time")
CLOCK_NAMES = METER_NAMES + WALL_CLOCK_NAMES

TIME_FREE_ROOTS = ("lib", "format")
TIME_FREE_MODULES = ("data.py", "descriptor.py", "schedule.py",
                     "store.py", "cli.py")

# meter-vs-clock law (user ruling 2026-08-30): measuring a thread's own
# CPU consumption is a METER, not a clock — it cannot order or gate
# behaviour and flows only into accounting fields (JobResult.cpu_s,
# EngineStat.consult_cpu_s). Wall/ordering sources are CLOCKS and are
# banned in production, save the one licensed lifecycle site below.
# process_time is a banned meter (the per-thread unification ruling).
METER_SITES = {
    "engine.py": 2, "plugins/place_sched.py": 2, "plugins/survey.py": 2,
    "plugins/tiles.py": 2, "plugins/refine.py": 2,
    "plugins/calibrate.py": 4, "plugins/color_refine.py": 2,
    "plugins/color_region.py": 7, "plugins/color_pooled.py": 2,
    "plugins/fields.py": 3, "plugins/local_ctx.py": 2,
    "plugins/plane_k.py": 2, "plugins/swim.py": 2,
    "plugins/uplift.py": 4}
# local_ctx keeps two meter sites across BOTH arms: the one job body
# they share starts the meter, and _attempt reads it once at the end.
# plane_k keeps two the same way: `planek_job` starts the meter and reads
# it on both exits (no cut, and the attempt).  swim keeps two for the
# same shape: `swim_job` starts the meter and reads it once at the end,
# whether or not the search produced a component to attempt.
# engine.py's one wall site is the safety-snapshot cadence
# (`_service_operator`, 2026-09-03): a lifecycle timer, never an ordering
# or a gate — the ruling's meter-vs-clock line holds.
WALL_LICENSED = {"diag/server.py": 2, "engine.py": 1}

LEGACY_RNG_NAMES = (
    "rand", "randn", "seed", "randint", "random_sample", "choice",
    "shuffle", "permutation", "normal", "uniform", "random",
    "standard_normal", "bytes")

LINE_CAP = 1000

LANDMINE_SOURCE = (
    "def only_a_landmine() -> int:\n"
    "    return h3_undefined_landmine_symbol\n")
LANDMINE_SYMBOL = "h3_undefined_landmine_symbol"

UNDEFINED_MESSAGES = (
    pyflakes_messages.UndefinedName,
    pyflakes_messages.UndefinedExport,
    pyflakes_messages.UndefinedLocal,
)


def _production_files() -> tuple[Path, ...]:
    return _h3_support.source_files(HOLO3_ROOT, exclude_dirs=EXCLUDED_DIRS)


def _measure_files() -> tuple[Path, ...]:
    return _h3_support.source_files(MEASURE_ROOT)


def _imported_modules(path: Path) -> tuple[tuple[str, int, int], ...]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, 0, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", node.level, node.lineno))
    return tuple(found)


def test_the_conversion_docs_archive_is_not_an_importable_package():
    archive = HOLO3_ROOT / "conversion_docs"
    assert archive.is_dir()
    assert not list(archive.rglob("__init__.py")), (
        "conversion_docs is excluded from the firewall and the pyflakes "
        "sweep only because nothing can import it")


def test_the_firewall_allowlist_is_exactly_the_declared_table():
    _h3_support.assert_golden(
        "firewall allowlist", tuple(sorted(FIREWALL_ALLOWLIST)),
        ("_h3_sims.py", "conftest.py", "test_h3_conventions.py",
         "test_h3_drift_declared.py", "test_h3_drift_format.py",
         "test_h3_drift_kernels.py", "test_h3_drift_receiver.py",
         "test_h3_page_domain.py"))
    for name, reason in sorted(FIREWALL_ALLOWLIST.items()):
        assert reason, name


def test_no_holo3_module_imports_v1_v2_or_the_session_scratch():
    _h3_support.skip_unless_slow_lane("the whole-tree import firewall sweep")
    checks = _h3_support.Checks("import firewall")
    for path in _production_files():
        if path.name in FIREWALL_ALLOWLIST:
            continue
        foreign = sorted(
            f"line {lineno}: {module}"
            for module, _level, lineno in _imported_modules(path)
            if module.split(".")[0] in FOREIGN_TREES)
        checks.equal(
            f"{path.relative_to(WORKTREE_ROOT)} imports no foreign tree",
            tuple(foreign), ())
    checks.assert_clean()


def test_the_firewall_gate_still_catches_a_planted_foreign_import(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text("import holo2.solve\nfrom holo.core import bch\n")
    foreign = [module for module, _level, _lineno
               in _imported_modules(planted)
               if module.split(".")[0] in FOREIGN_TREES]
    assert sorted(foreign) == ["holo.core", "holo2.solve"]


def test_only_the_allowlisted_test_modules_reach_across_trees():
    _h3_support.skip_unless_slow_lane("the whole-tree allowlist sweep")
    reaching = set()
    for path in _h3_support.source_files(TESTS_DIR):
        if any(module.split(".")[0] in FOREIGN_TREES
               for module, _level, _lineno in _imported_modules(path)):
            reaching.add(path.name)
    assert reaching <= set(FIREWALL_ALLOWLIST), sorted(
        reaching - set(FIREWALL_ALLOWLIST))


class _Collector:

    def __init__(self) -> None:
        self.undefined: list[str] = []
        self.broken: list[str] = []

    def unexpectedError(self, filename: str, message: str) -> None:
        self.broken.append(f"{filename}: {message}")

    def syntaxError(self, filename: str, message: str, lineno: int,
                    offset: int, text: str) -> None:
        self.broken.append(f"{filename}:{lineno}: {message}")

    def flake(self, message: object) -> None:
        if isinstance(message, UNDEFINED_MESSAGES):
            self.undefined.append(str(message))


def _pyflakes_undefined(paths: tuple[Path, ...]) -> _Collector:
    collector = _Collector()
    for path in paths:
        checkPath(str(path), collector)
    return collector


def test_no_undefined_name_survives_anywhere_the_gate_can_see(tmp_path):
    _h3_support.skip_unless_slow_lane("the whole-tree pyflakes sweep")
    landmine = tmp_path / "h3_landmine.py"
    landmine.write_text(LANDMINE_SOURCE)
    armed = _pyflakes_undefined((landmine,))
    assert len(armed.undefined) == 1, armed.undefined
    assert LANDMINE_SYMBOL in armed.undefined[0], (
        "the undefined-name gate has stopped detecting anything: a clean "
        "sweep from a disarmed gate is worth nothing")

    swept = _pyflakes_undefined(_production_files() + _measure_files())
    assert swept.broken == []
    assert swept.undefined == []


def test_the_pyflakes_sweep_actually_covers_both_trees():
    covered = _production_files() + _measure_files()
    assert len(covered) > 60
    roots = {path.relative_to(WORKTREE_ROOT).parts[0] for path in covered}
    assert roots == {"holo3", "measure"}


def _unseeded_rng_sites(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = (callee.attr if isinstance(callee, ast.Attribute)
                else callee.id if isinstance(callee, ast.Name) else "")
        if name == "default_rng" and not node.args and not node.keywords:
            found.append(f"line {node.lineno}: default_rng()")
        if (isinstance(callee, ast.Attribute)
                and name in LEGACY_RNG_NAMES
                and isinstance(callee.value, ast.Attribute)
                and callee.value.attr == "random"):
            found.append(f"line {node.lineno}: np.random.{name}()")
    return tuple(found)


def test_every_draw_in_the_tree_flows_from_an_explicit_seed():
    _h3_support.skip_unless_slow_lane("the whole-tree determinism sweep")
    checks = _h3_support.Checks("determinism")
    for path in _h3_support.source_files(HOLO3_ROOT,
                                         exclude_dirs=("__pycache__",)):
        checks.equal(
            f"{path.relative_to(WORKTREE_ROOT)} seeds every draw",
            _unseeded_rng_sites(path), ())
    checks.assert_clean()


def test_the_determinism_gate_still_catches_a_planted_unseeded_draw(
        tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import numpy as np\n"
        "a = np.random.default_rng()\n"
        "b = np.random.rand(4)\n"
        "good = np.random.default_rng(20260829)\n")
    found = _unseeded_rng_sites(planted)
    assert len(found) == 2, found
    assert "default_rng()" in found[0] and "np.random.rand()" in found[1]


def _clock_sites(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute)
                and node.attr in CLOCK_NAMES):
            found.append(f"line {node.lineno}: .{node.attr}")
        if (isinstance(node, ast.Attribute) and node.attr == "time"
                and isinstance(node.value, ast.Name)
                and node.value.id == "time"):
            found.append(f"line {node.lineno}: time.time")
    return tuple(found)



def _time_free_files() -> tuple[Path, ...]:
    found: list[Path] = []
    for name in TIME_FREE_ROOTS:
        found.extend(_h3_support.source_files(HOLO3_ROOT / name))
    for name in TIME_FREE_MODULES:
        found.append(HOLO3_ROOT / name)
    return tuple(found)


def _split_sites(path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    walls: list[str] = []
    meters: list[str] = []
    for site in _clock_sites(path):
        name = site.split(": ")[1].lstrip(".")
        (meters if name in METER_NAMES else walls).append(name)
    return tuple(walls), tuple(meters)


def test_the_kernels_and_the_format_law_touch_no_time_source():
    checks = _h3_support.Checks("time-free codec and format paths")
    for path in _time_free_files():
        checks.equal(f"{path.relative_to(WORKTREE_ROOT)} touches no time",
                     _clock_sites(path), ())
    checks.assert_clean()


def _time_law_files() -> tuple[Path, ...]:
    return _h3_support.source_files(
        HOLO3_ROOT, exclude_dirs=PRODUCTION_EXCLUDED_DIRS)


def _time_law_rels() -> tuple[str, ...]:
    files = _time_law_files()
    assert len(files) > 30, (
        f"the time law swept {len(files)} production files: a table keyed "
        "off files-found reads GREEN over an empty sweep, so the sweep "
        "itself is part of the law")
    return tuple(str(path.relative_to(HOLO3_ROOT)) for path in files)


def test_wall_clocks_are_banned_in_production_save_the_licensed_site():
    checks = _h3_support.Checks("wall-clock ban")
    rels = _time_law_rels()
    checks.equal("every licensed wall site still names a live file",
                 tuple(sorted(set(WALL_LICENSED) - set(rels))), ())
    for rel, path in zip(rels, _time_law_files()):
        walls, _meters = _split_sites(path)
        checks.equal(f"{rel} wall clocks", len(walls),
                     WALL_LICENSED.get(rel, 0))
    checks.assert_clean()


def test_meters_are_thread_time_only_and_enumerated():
    checks = _h3_support.Checks("meter table")
    rels = _time_law_rels()
    checks.equal("every metered file in the table still exists",
                 tuple(sorted(set(METER_SITES) - set(rels))), ())
    for rel, path in zip(rels, _time_law_files()):
        _walls, meters = _split_sites(path)
        checks.equal(f"{rel} process_time is banned",
                     meters.count("process_time"), 0)
        checks.equal(f"{rel} meter sites", len(meters),
                     METER_SITES.get(rel, 0))
    checks.assert_clean()


def test_the_engine_meter_is_the_consult_gauge():
    source = (HOLO3_ROOT / "engine.py").read_text()
    consult = source.split("def _close_consult")[1].split("\n    def ")[0]
    assert consult.count("thread_time") == 2, (
        "the engine's two meter reads are the consult gauge and must both "
        "live in _close_consult (EngineStat.consult_cpu_s)")


def test_the_clock_gate_still_catches_a_planted_clock(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import time\n"
        "a = time.thread_time()\n"
        "b = time.time()\n")
    assert len(_clock_sites(planted)) == 2


# Instrument dependencies that deliberately do NOT live in the working
# venv, keyed by the measure/ subtree that may import them.  An entry is
# a declaration that the driver runs under a second interpreter, and the
# reason it has to.  Adding one is a decision, not a workaround: it costs
# this gate's protection for that name, so it names the subtree too.
FOREIGN_INTERPRETER_IMPORTS: dict[str, tuple[str, str]] = {
    "mlx": ("accel",
            "Apple's array framework has no free-threaded 3.14 wheel; the "
            "measure/accel GPU drivers run under their own scratch venv"),
}


def _foreign_interpreter(head: str, path: Path) -> bool:
    entry = FOREIGN_INTERPRETER_IMPORTS.get(head)
    if entry is None:
        return False
    subtree, _reason = entry
    return subtree in path.relative_to(MEASURE_ROOT).parts[:-1]


def _resolves(module: str, level: int, path: Path) -> bool:
    if level:
        base = path.parent
        for _ in range(level - 1):
            base = base.parent
        if not module:
            return (base / "__init__.py").is_file()
        head = module.split(".")[0]
        return ((base / f"{head}.py").is_file()
                or (base / head / "__init__.py").is_file())
    head = module.split(".")[0]
    if head in sys.builtin_module_names:
        return True
    if _foreign_interpreter(head, path):
        return True
    for root in (MEASURE_ROOT, path.parent):
        if ((root / f"{head}.py").is_file()
                or (root / head / "__init__.py").is_file()):
            return True
    try:
        return importlib.util.find_spec(head) is not None
    except (ImportError, ValueError):
        return False


def test_every_import_in_the_by_path_instrument_drivers_still_resolves():
    checks = _h3_support.Checks("instrument rot")
    files = _measure_files()
    assert files, "no instrument drivers found under measure/"
    for path in files:
        missing = sorted(
            f"line {lineno}: {'.' * level}{module}"
            for module, level, lineno in _imported_modules(path)
            if not _resolves(module, level, path))
        checks.equal(
            f"{path.relative_to(WORKTREE_ROOT)} imports all resolve",
            tuple(missing), ())
    checks.assert_clean()


def test_the_instrument_rot_gate_still_catches_a_planted_dead_import(
        tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text("import numpy\nimport h3_module_that_never_existed\n")
    missing = [module for module, level, _lineno
               in _imported_modules(planted)
               if not _resolves(module, level, planted)]
    assert missing == ["h3_module_that_never_existed"]


def test_a_foreign_interpreter_import_is_excused_only_in_its_own_subtree():
    _h3_support.assert_golden(
        "foreign-interpreter imports",
        tuple(sorted(FOREIGN_INTERPRETER_IMPORTS)), ("mlx",))
    for name, (subtree, reason) in FOREIGN_INTERPRETER_IMPORTS.items():
        assert reason, name
        assert (MEASURE_ROOT / subtree).is_dir(), (
            f"{name} is excused for measure/{subtree}, which does not exist")
        assert _foreign_interpreter(
            name, MEASURE_ROOT / subtree / "driver.py")
        assert not _foreign_interpreter(
            name, MEASURE_ROOT / "somewhere_else" / "driver.py")
        assert not _foreign_interpreter(name, MEASURE_ROOT / "driver.py")
# --- the hand-built-pose gate ---------------------------------------
#
# `anchor.Affine` is one bare `tuple[float, ...]` alias serving TWO
# conventions half a cell apart: a `Placement.native_affine` must NOT
# carry the half cell (every consumer adds it), while the affine a
# `RegionWindow` carries and `anchor.pose_points` is handed MUST, because
# `pose_points` is a plain `M @ local + t`.  Nothing in the name or the
# type separates them, so copying either had even odds of being wrong —
# and THREE fixtures were found carrying the corner form on one day
# (2026-08-31), each reading every plane at a quarter of its contrast.
#
# The fix is unrepresentability, not a fourth guard: no fixture composes
# a pose by hand any more.  This gate keeps the deleted form deleted.
#
# SCOPE.  The `native_affine` convention is deliberately NOT covered:
# there the half cell is the consumer's to add, so a fixture that spells
# one is correct by construction (`measure/calibrate_stage_profile.py`
# and `measure/pava_benchmark.py` are the two, and their `-0.5` is the
# area-vs-index pixel convention, not a half cell).  What this gate bans
# is the POSE convention — the one that samples a raster.
POSE_DOORS = (
    "`color_region.region_window(store, wid)` (production, from a store)",
    "`holo3/tests/_h3_fixture_geometry.window_pose(row, placement)` "
    "(the same composer, from a Placement a fixture can build)")

#: callee name -> which argument is the pose affine
POSE_AFFINE_SINKS: dict[str, int] = {"pose_points": 0, "window_points": 1}

#: python's own name scopes, for resolving a pose affine's binding
SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
               ast.ClassDef, ast.Module)

#: hand-building one of these IS the defect: it is the object that
#: carries a pose into the sampler
POSE_CARRIERS = ("RegionWindow",)

#: every name either rule can fire on — the sweep's pre-filter
POSE_TRIGGERS = POSE_CARRIERS + tuple(POSE_AFFINE_SINKS)

#: FIREWALL_ALLOWLIST-style: file basename -> why it may still do this.
#: The claim this table makes is that a hand-built pose is a DEFECT
#: unless the geometry it carries is itself a recorded measurement.
POSE_GATE_ALLOWLIST: dict[str, str] = {
    "gt_bias.py":
        "replays e033's own recorded sheet-I page affine "
        "(`_sheet_i.tile_affine`) and displaces its translation by the "
        "MEASURED plane-common lock — recorded instrument truth, not "
        "composed geometry, so there is no production Placement to "
        "route through. Its corner handling was itself found and fixed "
        "by measurement (6e80ed8), which is the evidence this exemption "
        "rests on rather than an argument.",
}

PLANTED_CORNER_POSE = (
    "from holo3.plugins import color_region, color_region_anchor as anchor\n"
    "PPC = 6\n"
    "MARGIN_PX = 24\n"
    "def region_windows(row, span, index, wy, wx, local, page_cells):\n"
    "    affine = (float(PPC), 0.0, float(MARGIN_PX + wy * span * PPC),\n"
    "              0.0, float(PPC), float(MARGIN_PX + wx * span * PPC))\n"
    "    return color_region.RegionWindow(\n"
    "        patch_ordinal=index, window_id=('cap', 0, index, (0, 0, 1, 1)),\n"
    "        page=0, local_cells_yx=local, page_cells_yx=page_cells,\n"
    "        scan_points_yx=anchor.pose_points(affine, local),\n"
    "        shape_yx_cells=(span, span), affine=affine,\n"
    "        pitch_px=float(PPC))\n")

PLANTED_COMPOSED_POSE = (
    "from holo3.tests import _h3_fixture_geometry as geo\n"
    "def region_windows(row, placements):\n"
    "    return tuple(geo.window_pose(row, place) for place in placements)\n")

PLANTED_ALGEBRA_UNIT_TEST = (
    "import numpy as np\n"
    "from holo3.plugins import color_region_anchor as anchor\n"
    "def test_pose_points_is_the_affine_applied():\n"
    "    affine = (6.0, 0.1, 30.0, -0.2, 6.05, 40.0)\n"
    "    cells = np.asarray([[0, 0], [7, 9]], np.int64)\n"
    "    assert anchor.pose_points(affine, cells).shape == (2, 2)\n"
    "    assert anchor.window_points((10, 12), affine).shape == (4, 2)\n")


def _callee_name(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _scope_of(tree: ast.AST) -> dict[int, ast.AST]:
    """Each node's enclosing scope: a def, or the module itself.

    Name resolution has to be per-scope or the gate over-fires: one
    module holding both a fixture's computed affine and `pose_points`'
    own algebra tests would otherwise see the name `affine` bound to the
    fixture's tuple and flag the algebra.  Measured on the pre-fix
    `test_h3_plugins_color.py`: file-scoped resolution reported five
    sites where two are real.
    """
    owner: dict[int, ast.AST] = {id(tree): tree}

    def descend(node: ast.AST, scope: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            owner[id(child)] = scope
            descend(child, child if isinstance(child, SCOPE_NODES)
                    else scope)

    descend(tree, tree)
    return owner


def _six_tuple_literals(tree: ast.AST, owner: dict[int, ast.AST],
                        ) -> dict[int, dict[str, list[ast.Tuple]]]:
    """Per scope, the names bound there to a 6-element tuple display."""
    bound: dict[int, dict[str, list[ast.Tuple]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not isinstance(value, ast.Tuple) or len(value.elts) != 6:
            continue
        scope = bound.setdefault(id(owner.get(id(node), tree)), {})
        for target in node.targets:
            if isinstance(target, ast.Name):
                scope.setdefault(target.id, []).append(value)
    return bound


def _affine_argument(call: ast.Call, index: int) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == "affine":
            return keyword.value
    if len(call.args) > index:
        return call.args[index]
    return None


def _is_constant(node: ast.expr) -> bool:
    """A literal number, possibly negated or wrapped in `float(...)`."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp):
        return _is_constant(node.operand)
    if (isinstance(node, ast.Call) and _callee_name(node.func) == "float"
            and len(node.args) == 1 and not node.keywords):
        return _is_constant(node.args[0])
    return False


def _computed_translation(term: ast.Tuple) -> tuple[int, ...]:
    """Which of the affine's translation slots are page geometry.

    A pose affine's slots 2 and 5 are its pixel origin.  A LITERAL there
    is a unit test's datum — algebra over an arbitrary matrix, which is
    what `pose_points`' own tests do and must keep doing.  A COMPUTED
    one is a real page's geometry, and composing that is production's
    job, never a fixture's.
    """
    return tuple(slot for slot in (2, 5)
                 if not _is_constant(term.elts[slot]))


def _hand_built_pose_sites(path: Path) -> tuple[str, ...]:
    source = path.read_text()
    # Both rules fire only on a CALL to one of these, so a file whose
    # text does not contain the identifier cannot trip either — a strict
    # superset test, and it keeps the sweep a fast-lane cost: reading
    # ~200 files is cheap, parsing them all is not (measured 2.6 s
    # against 0.1 s).
    if not any(name in source for name in POSE_TRIGGERS):
        return ()
    return _hand_built_pose_sites_in(source, str(path))


def _hand_built_pose_sites_in(source: str, filename: str) -> tuple[str, ...]:
    tree = ast.parse(source, filename=filename)
    owner = _scope_of(tree)
    bound = _six_tuple_literals(tree, owner)
    module = bound.get(id(tree), {})
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee_name(node.func)
        if name in POSE_CARRIERS:
            found.append(
                (node.lineno,
                 f"line {node.lineno}: {name}(...) built by hand"))
            continue
        index = POSE_AFFINE_SINKS.get(name)
        if index is None:
            continue
        argument = _affine_argument(node, index)
        terms: list[ast.Tuple] = []
        if isinstance(argument, ast.Tuple) and len(argument.elts) == 6:
            terms.append(argument)
        elif isinstance(argument, ast.Name):
            local = bound.get(id(owner.get(id(node), tree)), {})
            terms.extend(local.get(argument.id, module.get(argument.id, ())))
        slots = sorted({slot for term in terms
                        for slot in _computed_translation(term)})
        if slots:
            found.append(
                (node.lineno,
                 f"line {node.lineno}: {name}(...) on a hand-built affine "
                 f"whose translation slots {slots} are computed"))
    return tuple(message for _lineno, message in sorted(found))


def _pose_gate_files() -> tuple[Path, ...]:
    return tuple(sorted(_measure_files()
                        + _h3_support.source_files(TESTS_DIR)))


def test_the_pose_gate_allowlist_is_exactly_the_declared_table():
    _h3_support.assert_golden("hand-built-pose allowlist",
                              tuple(sorted(POSE_GATE_ALLOWLIST)),
                              ("gt_bias.py",))
    for name, reason in sorted(POSE_GATE_ALLOWLIST.items()):
        assert reason, name


def test_no_fixture_composes_a_window_pose_by_hand():
    """THE UNREPRESENTABILITY GATE for the corner half-cell family.

    `test_h3_plugins_sampling_geometry` proves the two PRODUCTION
    composers agree, and `test_h3_uplift_existence` pins one fixture's
    pose against its own raster.  Neither stops a NEW fixture from
    hand-rolling the wrong half, which is how the same defect reached
    three files in a day.  This one does: the form is banned outright,
    and the message names the doors that replace it.
    """
    checks = _h3_support.Checks("hand-built window poses")
    files = _pose_gate_files()
    assert files, "the pose gate found no fixture files to sweep"
    doors = " OR ".join(POSE_DOORS)
    for path in files:
        if path.name in POSE_GATE_ALLOWLIST:
            continue
        found = _hand_built_pose_sites(path)
        checks.check(
            f"{path.relative_to(WORKTREE_ROOT)} composes no pose by hand",
            not found,
            f"{list(found)} — a window pose comes from {doors}, never "
            f"from a tuple written here: `Affine` serves two conventions "
            f"half a cell apart and nothing in the type tells them apart")
    checks.assert_clean()


def test_the_pose_gate_sweeps_both_the_instruments_and_the_suite():
    covered = _pose_gate_files()
    assert len(covered) > 40
    roots = {path.relative_to(WORKTREE_ROOT).parts[0] for path in covered}
    assert roots == {"holo3", "measure"}


def test_the_pose_gate_pre_filter_names_every_rule_it_short_circuits():
    """The pre-filter is what keeps this in the fast lane, and it is
    also the one way to disarm the gate by accident: a third rule keyed
    on a name no trigger mentions would never be reached."""
    assert set(POSE_TRIGGERS) == set(POSE_CARRIERS) | set(POSE_AFFINE_SINKS)
    planted = ("from holo3.plugins import color_region\n"
               "w = color_region.RegionWindow(affine=(1, 2, x, 4, 5, y))\n")
    assert any(name in planted for name in POSE_TRIGGERS)
    assert _hand_built_pose_sites_in(planted, "planted.py")


def test_the_pose_gate_still_catches_a_planted_corner_affine():
    """The mutation test: the deleted form, planted verbatim.

    `PLANTED_CORNER_POSE` is the pre-2026-08-31 `region_windows` body —
    the exact code that shipped the defect in three files — so a gate
    that stopped seeing it would be worth nothing.
    """
    found = _hand_built_pose_sites_in(PLANTED_CORNER_POSE, "planted.py")
    assert len(found) == 2, found
    joined = "\n".join(found)
    assert "RegionWindow(...) built by hand" in joined, found
    assert "pose_points(...) on a hand-built affine" in joined, found
    assert "[2, 5] are computed" in joined, found


def test_the_pose_gate_passes_the_composed_form_and_the_algebra_tests():
    assert _hand_built_pose_sites_in(
        PLANTED_COMPOSED_POSE, "composed.py") == ()
    assert _hand_built_pose_sites_in(
        PLANTED_ALGEBRA_UNIT_TEST, "algebra.py") == (), (
        "an arbitrary CONSTANT affine is a unit test's datum, not a "
        "page's geometry: banning it would only push the algebra tests "
        "into a helper and buy nothing")


def test_the_pose_gate_resolves_affine_names_per_scope():
    """One module, both idioms: only the fixture's sites are reported.

    `test_h3_plugins_color.py` was exactly this module before the
    reroute — a computed fixture pose beside `pose_points`' own algebra
    tests, both binding the name `affine`.  File-scoped resolution
    reported five sites where two are real.
    """
    corner_lines = len(PLANTED_CORNER_POSE.splitlines())
    found = _hand_built_pose_sites_in(
        PLANTED_CORNER_POSE + "\n" + PLANTED_ALGEBRA_UNIT_TEST.replace(
            "import numpy as np\n", "").replace(
            "from holo3.plugins import color_region_anchor as anchor\n", ""),
        "mixed.py")
    # file-scoped resolution reports four here: the algebra's own
    # `pose_points` and `window_points` inherit the fixture's binding
    assert len(found) == 2, found
    reported = tuple(int(message.split()[1].rstrip(":")) for message in found)
    assert max(reported) <= corner_lines, (found, corner_lines)


def _line_counts() -> tuple[tuple[Path, int], ...]:
    rows = []
    for path in _h3_support.source_files(
            HOLO3_ROOT, exclude_dirs=PRODUCTION_EXCLUDED_DIRS):
        rows.append((path, len(path.read_text().splitlines())))
    return tuple(sorted(rows, key=lambda row: -row[1]))


def test_no_production_module_has_grown_past_the_seam_signal():
    rows = _line_counts()
    assert len(rows) > 30, "the line-cap gate found almost no files"
    longest = ", ".join(
        f"{path.relative_to(WORKTREE_ROOT)}:{lines}"
        for path, lines in rows[:3])
    over = [(str(path.relative_to(WORKTREE_ROOT)), lines)
            for path, lines in rows if lines > LINE_CAP]
    assert over == [], (
        f"{over} exceed {LINE_CAP} lines: a line cap is a split-here "
        f"signal, never a budget to game (longest: {longest})")
