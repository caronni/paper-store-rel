"""W2 — `analyzer.fixedpoint`: the driver, and the blindness it claims.

The first three tests are the ones that matter: the import-set test of
PLAN §0 (no blind module may reach `truth` or `oracle`), the AST pin on
`blind_key` (the whole decision path, named so it can be pinned), and the
`wrong` abort.  Everything after that is plumbing, and the sheet-I leg
drives the fixture corpus's 22 residue tile-streams to a fixed point (3,
on the resume-3 run this was first written against).
"""

from __future__ import annotations

import ast
import base64
import copy
import dataclasses
import inspect
import json
import threading
from pathlib import Path

import numpy as np
import pytest

from analyzer import fixedpoint as fp
from analyzer import types as types_mod
from analyzer.types import VERDICT_CERTIFIED, AnalyzerConfig

from ._analyzer_fixtures import (RESIDUE_WITHHELD, damaged_residue_run_dir,
                                 fossil_i_inputs, needs_sim, residue_census,
                                 residue_run, sim_run)
#: the synthetic driver fixture — one stub of `blind_key`/`_retarget`
#: for the whole suite, kept where the progress tests built it
from .test_analyzer_progress import _FakeRun, _stubbed_driver

PACKAGE = Path(fp.__file__).resolve().parent

#: PLAN §0: these decide, so none of them may see the score column.
FORBIDDEN = ("truth", "oracle")


def test_blind_key_mentions_neither_truth_nor_oracle():
    """The AST pin of DESIGN §0 on the analyzer's decision path."""
    tree = ast.parse((PACKAGE / "fixedpoint.py").read_text("utf-8"))
    function = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "blind_key")
    seen: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
    for banned in ("truth", "oracle", "truth_mod", "oracle_mod",
                   "user_bits_gt", "score_evidence", "score_key"):
        assert banned not in seen, (
            f"blind_key references {banned!r} — the blind path must be "
            f"blind by construction, not by convention")


def test_the_driver_has_no_truth_door_at_all():
    """RULED 2026-09-04: not `blind_key` only — the whole module.

    `fixedpoint` used to hold `score_key`, which took a `Truth` and
    filled the ledger's oracle side table.  Both are gone: the driver
    has no truth argument, no truth import, and no function that reads
    one.  What was `score_key` now lives in `analyzer.score`, offline.
    """
    tree = ast.parse((PACKAGE / "fixedpoint.py").read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute)):
            name = getattr(node, "id", None) or getattr(node, "attr", "")
            assert name not in ("truth_mod", "oracle_mod", "score_key",
                                "score_evidence", "score_rung"), name
    names = {node.name for node in ast.walk(tree)
             if isinstance(node, ast.FunctionDef)}
    assert "score_key" not in names
    signature = inspect.signature(fp.run)
    assert "truth" not in signature.parameters
    assert "allow_wrong" not in signature.parameters


#: The OFFLINE lanes of the package — the ones a run command may not
#: reach.  `score` is the scoring door, `truth`/`oracle` are what it
#: opens, and `sweeps` is the record of finished measurements, which
#: loads a payload directly (`analyzer/sweeps/*.py`).  Everything else
#: under `analyzer/`, subpackages included, is a run module, so the
#: closure below starts from all of them.
SCORING_ONLY = ("truth", "oracle", "score", "sweeps")


def _module_file(name: str) -> Path | None:
    """`"planeview.emit"` -> its path; a package resolves to __init__."""
    stem = PACKAGE.joinpath(*name.split("."))
    if stem.with_suffix(".py").exists():
        return stem.with_suffix(".py")
    if (stem / "__init__.py").exists():
        return stem / "__init__.py"
    return None


def _package_modules() -> list[str]:
    """Every module under `analyzer/`, dotted, subpackages included.

    `tests/` is not shipped code and imports whatever it verifies, this
    module included; it is not part of any run path.
    """
    out: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        if "__pycache__" in path.parts or path.stem == "__main__":
            continue
        if path.relative_to(PACKAGE).parts[0] == "tests":
            continue
        parts = path.relative_to(PACKAGE).parts
        dotted = ".".join(parts[:-1] if path.stem == "__init__"
                          else parts[:-1] + (path.stem,))
        if dotted:
            out.add(dotted)
    return sorted(out)


def _named_modules(nodes, own: str = "") -> set[str]:
    """The analyzer modules the given import NODES name.

    Relative imports are resolved against the importer's OWN package, so
    `analyzer/planeview/emit.py`'s `from .. import frame` lands on
    `frame` and its `from .row import PLANE_OF` on `planeview.row`.

    BOTH spellings of a relative import count (review, 2026-09-04): the
    bare `from . import truth` AND `from .truth import TruthError`.  The
    CLI twin of this extractor read only the first, so a MODULE-LEVEL
    `from .truth import TruthError` in `cli.py` passed both guards —
    confirmed by mutation.  One extractor now serves both callers.
    """
    candidates: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = own.split(".") if own else []
                base = base[:len(base) - (node.level - 1)] \
                    if node.level > 1 else base
                head = ".".join([*base, *(node.module.split(".")
                                          if node.module else [])])
            elif (node.module or "").startswith("analyzer"):
                head = (node.module or "").partition("analyzer.")[2]
            else:
                continue
            if head:
                candidates.add(head)
            candidates.update(f"{head}.{alias.name}" if head else alias.name
                              for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("analyzer."):
                    candidates.add(alias.name.partition("analyzer.")[2])
    return {item for item in candidates if _module_file(item) is not None}


def _local_imports(name: str) -> set[str]:
    """The analyzer modules `name` imports, at ANY nesting depth."""
    path = _module_file(name)
    assert path is not None, name
    own = name if path.name == "__init__.py" else name.rpartition(".")[0]
    return _named_modules(ast.walk(ast.parse(path.read_text("utf-8"))), own)


def test_no_module_reachable_from_a_run_command_imports_truth_or_oracle():
    """The import-set test of PLAN §0, extended to the CLOSURE (2026-09-04).

    The old test named ten modules and checked their direct imports; the
    ruling is stronger than that — NO module a run command can reach may
    import `analyzer.truth` or `analyzer.oracle`, however many hops
    away, and a hop through a SUBPACKAGE is still a hop.  So the graph
    is walked over every module under `analyzer/` including
    `planeview/`: each is a root unless it is one of the offline lanes,
    `cli` contributes only its MODULE-LEVEL imports (its one
    function-local import of `score` is the scoring door, pinned by the
    test below), and the closure must not contain truth or oracle.
    """
    graph = {name: _local_imports(name) for name in _package_modules()}
    graph["cli"] = _cli_module_level_imports()
    assert "planeview.emit" in graph, "the subpackage is in the graph"
    assert "frame" in graph["planeview.emit"], "…and its `..` hops resolve"
    seen: set[str] = set()
    stack = [name for name in graph
             if name.split(".")[0] not in SCORING_ONLY]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack.extend(graph.get(name, ()))
    banned = {item for item in seen
              if item.split(".")[0] in ("truth", "oracle")}
    assert not banned, (
        f"a run module reaches {sorted(banned)}; "
        f"reachable set: {sorted(seen)}")
    assert not {item for item in seen if item.split(".")[0] == "score"}
    # The roots really are the whole run side, not a shrunken list.
    assert {"cli", "fixedpoint", "arms", "planeview", "planeview.drive",
            "field2", "unionbase", "export_facts"} <= seen


def _cli_module_level_imports() -> set[str]:
    """`cli.py`'s TOP-LEVEL imports only, both relative spellings."""
    tree = ast.parse((PACKAGE / "cli.py").read_text("utf-8"))
    return _named_modules(tree.body)


def test_the_cli_reaches_score_only_inside_cmd_score():
    """One door, and it is a named one."""
    tree = ast.parse((PACKAGE / "cli.py").read_text("utf-8"))
    holders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        reached = _named_modules(ast.walk(node))
        if reached & {"score", "truth", "oracle"}:
            holders.append(node.name)
    assert sorted(set(holders)) == ["cmd_score", "truth_error"]
    assert not _cli_module_level_imports() & {"score", "truth", "oracle"}


def test_a_module_level_truth_import_in_the_cli_would_be_caught():
    """The mutation that used to slip past both guards (2026-09-04).

    `from .truth import TruthError` at `cli.py`'s top level is exactly
    the breach the ruling forbids; the extractor must SEE it.  Pinned on
    the source text rather than by editing the file.
    """
    source = (PACKAGE / "cli.py").read_text("utf-8").replace(
        "from . import close as close_mod",
        "from .truth import TruthError\nfrom . import close as close_mod", 1)
    assert "truth" in _named_modules(ast.parse(source).body)


# ------------------------------------------------------------- plumbing

def test_expand_rungs_turns_l7_into_both_erasure_rungs():
    assert fp.expand_rungs(("L0", "L7")) == ("L0", "L7a", "L7b")
    assert fp.expand_rungs(("L7a",)) == ("L7a",)


def test_battery_drops_the_stream_specific_arms():
    config = AnalyzerConfig()
    assert "subtract+word" in config.battery_for("C")
    assert "subtract+word" not in config.battery_for("Y")
    assert config.battery_for("Y")[0] == "subtract+offset"


def test_refused_arms_leave_the_battery():
    config = AnalyzerConfig(refused_arms=("subtract+field",))
    assert "subtract+field" not in config.battery_for("C")
    assert "subtract+field+offset" in config.battery_for("C")


def test_the_shared_exposure_never_overshoots_its_bound_on_threads():
    """The bound is a wall, not an average (review F13, 2026-09-13).

    Eight threads proposing 500 DISTINCT digests each against a bound
    that pays for 200: the old check-then-act pair let as many as one
    per worker through after the wall, which is how a pass ended over a
    bound DESIGN §0 calls a correctness bound.  Exactly 200 here, and
    the charges sum to the same 200.
    """
    exposure = fp.shared_exposure(200 * 2.0 ** -32)
    charged: list[int] = []

    def worker(base: int) -> None:
        mine = 0
        for index in range(500):
            _allowed, n_new = exposure.reserve(
                bytes([base, index % 256, index // 256]))
            mine += n_new
        charged.append(mine)

    threads = [threading.Thread(target=worker, args=(base,))
               for base in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert exposure.distinct == 200
    assert sum(charged) == 200
    assert exposure.expected_false == pytest.approx(200 * 2.0 ** -32)
    assert not exposure.exceeded()


def test_one_digest_proposed_by_every_thread_is_charged_once():
    """The other half of the race: `n_new` is the rung's own charge, so
    a digest two workers propose at the same moment may be paid for
    once — by one of them."""
    exposure = fp.shared_exposure()
    charged: list[int] = []
    start = threading.Barrier(8, timeout=10)

    def worker() -> None:
        start.wait()
        charged.append(exposure.reserve(b"one codeword")[1])

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert exposure.distinct == 1
    assert sorted(charged) == [0] * 7 + [1]


def test_a_copied_exposure_shares_the_lock_with_the_set_it_guards():
    """M7: `consulted` is copied by reference, so the lock must be too.

    `dataclasses.replace` re-defaults `init=False` fields and does not
    dispatch to `__replace__` (3.14.7), so a lock that did not ride in
    the init gave two locks over one set — F13's race again, through a
    copy.  No caller does this today; the type stops it either way.
    """
    original = fp.shared_exposure()
    copied = dataclasses.replace(original, bound_expected_false=1.0)
    assert copied._lock is original._lock
    assert copied.consulted is original.consulted
    assert copy.replace(original, bound_expected_false=1.0)._lock \
        is original._lock


def test_shared_exposure_takes_a_bound():
    exposure = fp.shared_exposure(1e-9)
    assert exposure.bound_expected_false == 1e-9
    assert exposure.would_exceed(100) is True


def test_retarget_covers_the_neighbourhood_and_the_siblings():
    class _Row:
        streams = tuple(type("S", (), {"stream_id": name})()
                        for name in ("C", "M", "Y"))

    class _Inputs:
        row = _Row()
        tiles_yx = (4, 4)
        certificates: dict = {}

    out = fp._retarget(_Inputs(), (0, 1, 1, "C"), set(), set())
    assert (0, 1, 1, "M") in out and (0, 1, 1, "Y") in out
    assert len([key for key in out if key[3] == "C"]) == 8
    assert (0, 1, 1, "C") not in out


def test_retarget_skips_what_is_already_done():
    class _Row:
        streams = tuple(type("S", (), {"stream_id": name})()
                        for name in ("C", "M", "Y"))

    class _Inputs:
        row = _Row()
        tiles_yx = (4, 4)
        certificates = {(0, 0, 1, "C"): object()}

    out = fp._retarget(_Inputs(), (0, 1, 1, "C"), {(0, 2, 1, "C")},
                       {(0, 1, 1, "M")})
    assert (0, 0, 1, "C") not in out       # already a production certificate
    assert (0, 2, 1, "C") not in out       # certified this pass
    assert (0, 1, 1, "M") not in out       # already attempted


def test_row_for_falls_back_to_a_bare_row():
    row = fp._row_for({}, (0, 5, 6, "Y"))
    assert row.key == (0, 5, 6, "Y") and row.esi == -1
    assert row.covered is True


def test_retarget_re_attacks_a_key_an_earlier_generation_tried():
    """The W3 cascade ruling: the driver's exclusion set is EMPTY."""
    class _Row:
        streams = tuple(type("S", (), {"stream_id": name})()
                        for name in ("C", "M", "Y"))

    class _Inputs:
        row = _Row()
        tiles_yx = (4, 4)
        certificates: dict = {}

    out = fp._retarget(_Inputs(), (0, 1, 1, "C"), set(), set(), {})
    assert (0, 0, 0, "C") in out and (0, 1, 1, "Y") in out
    source = Path(fp.__file__).read_text("utf-8")
    assert "_retarget(inputs, key, certified, set()," in source, (
        "run() must hand _retarget an EMPTY attempted set, or a key an "
        "earlier generation failed on is never re-attacked")


def test_row_verdict_has_only_the_three_blind_outcomes():
    """2026-09-04: `wrong` and `false_accept` left with truth.

    A run can say `open`, `certified` or `certified_list` and nothing
    else, so there is no stickiness left to carry across a re-attack:
    the row describes the attempt whose evidence it holds.
    """
    assert fp.row_verdict(["open", "certified"],
                          has_certificate=True) == "certified"
    assert fp.row_verdict(["open", "certified_list"],
                          has_certificate=True) == "certified_list"
    assert fp.row_verdict(["certified_list", "certified"],
                          has_certificate=True) == "certified"
    assert fp.row_verdict(["refused", "below_floor"],
                          has_certificate=False) == "open"
    assert fp.VERDICT_PRECEDENCE == ("certified", "certified_list", "open")


def test_the_ledger_row_keeps_the_packed_hard_vector(tmp_path):
    """What the offline scorer needs, and only the run can produce."""
    from analyzer.types import RungResult
    result = RungResult(rung="L1", verdict="open", user_bits=None,
                        n_iters=150, unsat_at_exit=9, syndrome_ok=False,
                        posterior_summary={}, crc_consults_distinct=0,
                        seconds=0.5, detail={"hard_packed": b"\x00\x01\x02",
                                             "mode": "minsum-then-sp"})
    stored = fp._rung_dict(result)
    assert "hard_packed" not in stored["detail"]
    assert stored["detail"]["hard_packed_b64"] == "AAEC"
    assert base64.b64decode(stored["detail"]["hard_packed_b64"]) == \
        b"\x00\x01\x02"
    assert stored["detail"]["mode"] == "minsum-then-sp"   # the rest passes
    assert stored["unsat_at_exit"] == 9 and stored["n_iters"] == 150


def test_a_reused_arm_row_says_so_in_the_ledger_diag(monkeypatch):
    """The collapsed-field economy is visible where a reader looks.

    A row whose arms took an already-computed twin instead of a second
    evaluation carries the count; each such (lane, arm) row names its
    twin under `reused_from_arm`.  A pass that reused nothing does not
    carry the key at all, so the ledger does not grow a column for a
    zero.
    """
    key = (0, 0, 0, "C")
    config = AnalyzerConfig(workers=1, max_generations=1, rungs=("L0",),
                            rules=("sum",))
    monkeypatch.setattr(fp, "_retarget", lambda *args, **kwargs: [])
    monkeypatch.setattr(fp.inputs_mod, "metadata_bit", lambda *args: 0)

    monkeypatch.setattr(fp, "blind_key", lambda *args, **kwargs: {
        "seconds": 0.0, "n_lanes": 1, "reused_arms": 2})
    ledger = fp.run(_FakeRun(), [key], config)
    assert ledger.rows[0].diag["reused_arm_evaluations"] == 2

    monkeypatch.setattr(fp, "blind_key", lambda *args, **kwargs: {
        "seconds": 0.0, "n_lanes": 1})
    ledger = fp.run(_FakeRun(), [key], config)
    assert "reused_arm_evaluations" not in ledger.rows[0].diag


def test_keep_hard_is_on_by_default_in_the_driver(monkeypatch):
    """The knob the ledger row depends on is not left to a caller.

    Behavioural since 2026-09-20 (it used to grep `fixedpoint.py` for the
    literal): one synthetic pass with an EMPTY `config.knobs`, and every
    rung the ladder returns carries the packed hard vector — which the
    ladder writes only under `keep_hard`, so the driver supplied it.
    """
    from .test_analyzer_gaps_fix import _reroll_world
    inputs, built = _reroll_world(monkeypatch)
    config = AnalyzerConfig(arms=("head+offset",), rules=("sum",),
                            rungs=("L0",), all_rules=False)
    assert dict(config.knobs) == {}            # nothing asked for it
    out = fp.blind_key(inputs, {}, built.key, config, fp.shared_exposure())
    results = out["rungs"]["sum"]
    assert results and all("hard_packed" in item.detail for item in results)
    assert "hard_packed_b64" in fp._rung_dict(results[0])["detail"]


# ------------------------------ the generation cap and the stop reason
#
# Ruling R1 (2026-09-06): `--max-generations N` and `--fixed-point` are
# orthogonal.  These run the driver over the synthetic cascade of
# `test_analyzer_progress` — every decision stubbed, so what is under
# test is the loop's bound and the reason it records, nothing else.


def _cascade(monkeypatch, *, depth: int) -> list:
    """A stubbed cascade `depth` generations deep: every key certifies
    and hands the next one a single re-attack.  Returns the targets."""
    keys = [(0, 0, index, "C") for index in range(depth + 1)]
    _stubbed_driver(monkeypatch, certify=set(keys),
                    follow_ups={key: (nxt,)
                                for key, nxt in zip(keys, keys[1:])})
    return keys[:1]


def _capped(cap: int) -> AnalyzerConfig:
    return AnalyzerConfig(workers=1, max_generations=cap,
                          rungs=("L0",), rules=("sum",))


def test_the_cap_runs_its_generations_with_no_fixed_point_flag(monkeypatch):
    """N alone runs N generations while re-attacks keep arriving."""
    targets = _cascade(monkeypatch, depth=6)
    ledger = fp.run(_FakeRun(), targets, _capped(3))
    assert ledger.header["generations_run"] == 3
    assert ledger.header["max_generations"] == 3
    assert ledger.header["fixed_point"] is False
    assert ledger.header["stop_reason"] == fp.STOP_CAP_REACHED


def test_the_cap_stops_early_when_a_generation_re_attacks_nothing(
        monkeypatch):
    """A cap is a BOUND, never a demand for N generations of work."""
    targets = _cascade(monkeypatch, depth=1)
    ledger = fp.run(_FakeRun(), targets, _capped(8))
    assert ledger.header["generations_run"] == 2      # not 8
    assert ledger.header["stop_reason"] == fp.STOP_FIXED_POINT


def test_a_one_generation_pass_says_the_cap_stopped_it(monkeypatch):
    """A cap of one is a cap: the reason says so and the header says
    which cap it was (follow-up review — the retired `single generation`
    reason claimed to know a spelled `--max-generations 1` from the
    default, and nothing in the driver can)."""
    targets = _cascade(monkeypatch, depth=2)
    ledger = fp.run(_FakeRun(), targets, _capped(1))
    assert ledger.header["generations_run"] == 1
    assert ledger.header["stop_reason"] == fp.STOP_CAP_REACHED
    assert ledger.header["max_generations"] == 1
    assert ledger.header["fixed_point"] is False
    assert not hasattr(fp, "STOP_SINGLE_GENERATION")


def test_a_cap_below_one_is_refused_by_the_config_not_run_as_zero(
        monkeypatch):
    """The library boundary holds R1's floor, not only the CLI's."""
    with pytest.raises(ValueError, match="max_generations"):
        AnalyzerConfig(max_generations=0)
    with pytest.raises(ValueError, match="max_generations"):
        AnalyzerConfig(max_generations=-3)


def test_one_generation_that_re_attacks_nothing_is_a_fixed_point(
        monkeypatch):
    """The bound did not bind: nothing certified, so nothing followed."""
    _stubbed_driver(monkeypatch, certify=set(), follow_ups={})
    ledger = fp.run(_FakeRun(), [(0, 0, 0, "C")], _capped(1))
    assert ledger.header["stop_reason"] == fp.STOP_FIXED_POINT


def test_the_header_records_the_convergence_request_beside_the_cap(
        monkeypatch):
    """Both values, so a ledger says which bound the operator asked for
    and whether the pass converged under it."""
    targets = _cascade(monkeypatch, depth=1)
    ledger = fp.run(_FakeRun(), targets, _capped(8), fixed_point=True)
    assert ledger.header["fixed_point"] is True
    assert ledger.header["max_generations"] == 8
    assert ledger.header["stop_reason"] == fp.STOP_FIXED_POINT


# ------------------------------------------- the leg on a decoded run
# TIER S (2026-10-09): the receiver's colour sim decoded into a run dir,
# with `RESIDUE_WITHHELD`'s certificates taken out of its snapshot and
# its rasters through the DAMAGED channel — on the clean residue all
# twelve certify in generation 0 on `sum`/L0 and nothing after it runs.
# Sheet I's 11 of 22 is a record (PAGE-FIELD-PLAN A1b).

#: Q1.6 on the DAMAGED residue, measured 2026-10-09: ten certify in
#: generation 0 (three by a re-roll), the corner (0, 0, 0, C) is
#: re-attacked in generation 1 after (0, 0, 1, C) and stays open with
#: (0, 4, 9, Y); ~40 s at four workers.
RESIDUE_CERTIFIED = 10
RESIDUE_OPEN = ((0, 0, 0, "C"), (0, 4, 9, "Y"))


@needs_sim
def test_a_residue_runs_to_a_fixed_point():
    """Q1.6: the battery + L0-L3 + L7 over a withheld, damaged residue.

    The residue is the withheld set exactly, by construction.  The
    certified count, the open keys and the second generation are a
    measurement of this tree on this stimulus; that every certified
    row's bits are the certificate the RECEIVER minted for the key,
    withheld from the snapshot the pass read, is not — and needs no
    truth.
    """
    from holo.receiver.tests._h3_support import assert_measured

    from analyzer import inputs, residue as residue_mod
    run = inputs.load_run(damaged_residue_run_dir())
    rows = residue_mod.census(run)
    residue = [row for row in rows
               if row.covered and not row.certified_by_production]
    assert {row.key for row in residue} == set(RESIDUE_WITHHELD)
    config = AnalyzerConfig(workers=4, rules=("sum", "best"),
                            rungs=("L0", "L1", "L2", "L3", "L7"),
                            max_generations=8)
    ledger = fp.run(run, residue, config, census_rows=rows)

    assert [row.key for row in ledger.rows[:len(residue)]] \
        == [row.key for row in residue]
    certified = [row for row in ledger.rows
                 if row.verdict == VERDICT_CERTIFIED]
    print(f"\nQ1.6 residue: {len(certified)}/{len(ledger.rows)} certified "
          f"in {ledger.header['seconds']:.1f}s, exposure "
          f"{ledger.header['exposure_distinct']} distinct "
          f"(E[false] {ledger.header['exposure_expected_false']:.3g})")
    for row in ledger.rows:
        print(f"  {row.key} {row.verdict} gen={row.generation} "
              f"rule={row.certifying_rule} rung={row.certifying_rung} "
              f"lanes={row.diag.get('n_lanes')} "
              f"attempts={row.diag.get('attempts')}")
    assert {row.verdict for row in ledger.rows} <= {VERDICT_CERTIFIED,
                                                    "certified_list", "open"}
    minted = sim_run().certificates
    for row in certified:
        assert np.array_equal(
            np.asarray(row.rungs["user_bits"], np.uint8),
            np.asarray(minted[row.key].user_bits, np.uint8)), row.key
    assert_measured("Q1.6 certified on the damaged residue",
                    len(certified), RESIDUE_CERTIFIED)
    assert_measured("Q1.6 open on the damaged residue",
                    tuple(sorted(row.key for row in ledger.rows
                                 if row.verdict == "open")), RESIDUE_OPEN)
    assert ledger.header["stop_reason"] == fp.STOP_FIXED_POINT
    assert_measured("Q1.6 last generation on the damaged residue",
                    max(row.generation for row in ledger.rows), 1)
    for row in ledger.rows:
        for rule, batch in row.rungs.items():
            if rule == "user_bits":
                continue
            assert any("hard_packed_b64" in item["detail"]
                       for item in batch), rule


@needs_sim
def test_the_ledger_is_worker_count_independent_in_its_order():
    """Four workers retire keys out of order; the ledger does not.

    Ten rows of a withheld residue over four workers already
    interleave: what is under test is the driver's ordering of retired
    rows against the order it was handed, with the real arms.
    """
    run = residue_run()
    rows = residue_census()
    residue = [row for row in rows
               if row.covered and not row.certified_by_production][:10]
    assert len(residue) == 10
    config = AnalyzerConfig(workers=1, arms=("subtract+committed",),
                            rules=("sum",), rungs=("L0",),
                            max_generations=1)
    serial = fp.run(run, residue, config, census_rows=rows)
    parallel = fp.run(run, residue,
                      AnalyzerConfig(workers=4, arms=("subtract+committed",),
                                     rules=("sum",), rungs=("L0",),
                                     max_generations=1),
                      census_rows=rows)
    assert [row.key for row in serial.rows] == [row.key
                                                for row in parallel.rows]
    for left, right in zip(serial.rows, parallel.rows):
        for rule in left.rungs:
            if rule == "user_bits":
                continue
            assert [item["unsat_at_exit"] for item in left.rungs[rule]] == \
                [item["unsat_at_exit"] for item in right.rungs[rule]]


# `test_sheet_i_wrong_certificate_aborts_the_run` is RETIRED: a run has
# no truth to disagree with any more, so there is nothing to abort on.
# The certificate check it stood for is `analyzer score`'s WRONG report,
# tested against a deliberately mismatched payload in
# `test_analyzer_score.py`.


def test_the_metadata_bit_is_every_certificates_first_user_bit():
    """Over sheet I's identity, every one of its 5,883 tile-streams.

    The word comes from the run's own certified equations (F3: the
    receiver's metadata solve over the emitted certificates); the bit at
    each key must be what the encoder put in `user_bits[0]`.
    """
    run = fossil_i_inputs()
    from analyzer import inputs as inputs_mod
    assert run.metadata_state == "ready"
    assert len(run.certificates) == 5883
    for key, certificate in run.certificates.items():
        bit = inputs_mod.metadata_bit(run, key)
        assert bit in (0, 1)
        assert int(np.asarray(certificate.user_bits)[0]) == bit, key


# ------------------- leg 4: independent agreement and the refusal (W7)
#
# The pass driver's whole adjudication of `combine.independent_agreement`
# is `fp.adjudicate`, so it is tested here directly rather than through a
# run dir: agreeing certificates keep theirs and carry the count,
# disagreeing ones lose it.


class _Result:
    """A RungResult as far as `_claims_of` reads one."""

    def __init__(self, verdict, bits, rung="L0"):
        self.verdict = verdict
        self.rung = rung
        self.user_bits = None if bits is None else np.asarray(bits, np.uint8)


_SUMMARY_TWO = {"lanes": (("aaaaaaaaaaaa", 3), ("bbbbbbbbbbbb", 3)),
                "coefficients": (1.0, 1.0)}
_SUMMARY_BEST_A = {"lanes": (("aaaaaaaaaaaa", 3), ("bbbbbbbbbbbb", 3)),
                   "coefficients": (1.0, 0.0)}
_SUMMARY_BEST_B = {"lanes": (("aaaaaaaaaaaa", 3), ("bbbbbbbbbbbb", 3)),
                   "coefficients": (0.0, 1.0)}
_BITS = np.array([1, 1, 0, 1, 0, 0, 1, 0], np.uint8)
_OTHER = np.array([1, 1, 0, 1, 0, 0, 1, 1], np.uint8)


def test_claims_of_takes_only_the_gate_passing_rungs():
    claims = fp._claims_of(
        [_Result("open", None, "L0"), _Result("certified", _BITS, "L1"),
         _Result("certified_list", _BITS, "L4")], "sum", _SUMMARY_TWO)
    assert [item.rung for item in claims] == ["L1", "L4"]
    assert all(item.captures == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}
               for item in claims)


def test_claims_of_reads_the_captures_a_rule_actually_used():
    claims = fp._claims_of([_Result("certified", _BITS)], "best",
                           _SUMMARY_BEST_A)
    assert claims[0].captures == {"aaaaaaaaaaaa"}


def test_adjudicate_keeps_a_certificate_two_captures_agree_on():
    kept, agreement = fp.adjudicate(
        ("best", "L0", _BITS),
        fp._claims_of([_Result("certified", _BITS)], "best", _SUMMARY_BEST_A)
        + fp._claims_of([_Result("certified", _BITS)], "best2",
                        _SUMMARY_BEST_B))
    assert kept is not None
    assert agreement["independent_agreement"] == 2
    assert agreement["contradiction"] is False


def test_adjudicate_refuses_the_key_when_two_certificates_disagree():
    """Never mint on a contradiction — there is no blind way to choose."""
    kept, agreement = fp.adjudicate(
        ("best", "L0", _BITS),
        fp._claims_of([_Result("certified", _BITS)], "best", _SUMMARY_BEST_A)
        + fp._claims_of([_Result("certified", _OTHER)], "best2",
                        _SUMMARY_BEST_B))
    assert kept is None
    assert agreement["contradiction"] is True
    assert agreement["independent_agreement"] == 0


def test_adjudicate_leaves_an_uncertified_key_alone():
    kept, agreement = fp.adjudicate(None, [])
    assert kept is None
    assert agreement["n_claims"] == 0
    assert agreement["contradiction"] is False


def test_the_refusal_string_is_the_one_the_driver_writes():
    assert fp.CONTRADICTION_REFUSAL == "independent_certificates_disagree"
    source = inspect.getsource(fp.run)
    assert "CONTRADICTION_REFUSAL" in source
    assert "independent_agreement" in source




# ---------------------------------------- the in-run `field2.json` (A2)
#
# The product a ladder writes beside its ledger: the pooled `field2`
# fields the pass's own arms fitted, read back from the memo, in the
# schema `measure/page_field/compare.py --analyzer` reads.  The pooled
# fit itself is stubbed — it needs rasters, and what is under test here
# is the PRODUCT, not the estimator (`test_analyzer_field2.py` owns
# that), so the tiny world is one page, one lane and planted grids.

_FIELD2_TILES_YX = (6, 12)

#: 64 cells x `cell_dots` dots at 600 dpi: 5.4187 mm/tile at c2 and
#: 8.128 at c3, which is the 1.5x a hardcoded 2 would get wrong.
_FIELD2_MM_C2 = 64.0 * 2.0 / 600.0 * 25.4
_FIELD2_MM_C3 = 64.0 * 3.0 / 600.0 * 25.4


class _Field2Row:
    """A format row with the one field `color_sites.cell_dots_of` reads."""

    def __init__(self, cell_dots: int) -> None:
        self.pitch_in = cell_dots / 600.0


class _Field2Placement:
    def __init__(self, page: int) -> None:
        self.page = int(page)


class _Field2Lane:
    """A lane with an id and a placement; the fit that would read it is
    stubbed, so no pixel of a lane is reached.

    The placement is what `field2.lanes_for_page` filters on, and the
    product asks it which lanes THIS pass's fit would have pooled (M2),
    so a lane without one is not a lane the comparison can be made
    against.
    """

    def __init__(self, capture: str, level: int, page: int = 0) -> None:
        self.lane_id = (capture, level)
        self.placements = (_Field2Placement(page),)


class _StandingField:
    """The production fact the pass read — only `ordinal` is taken from
    it (`holo.receiver.data.PlaneField`)."""

    def __init__(self, ordinal: int) -> None:
        self.ordinal = int(ordinal)


#: One weighted tile record — enough that `PageField.tiles` is not
#: empty, which is what separates a fit from a refusal.
_TILE_OFFSET = fp.field2_mod.TileOffset(
    ty=0, tx=0, offset_dots_xy=(0.0, 0.0), n_labels=12, n_discriminating=12,
    committed_logloss=0.5, search_logloss=0.4, gain=0.1, curvature=0.2,
    weight=1.0)


def _planted_field(stream: str, plane: int, amplitude: float,
                   supported: bool = True):
    """A pooled `PageField` with one sinusoid on x.

    `supported=False` is what `field_from_pooled` returns when no
    furniture anchor stood: zero grids and an EMPTY `tiles`, which is a
    refusal and not a field of zeros.
    """
    tiles_y, tiles_x = _FIELD2_TILES_YX
    delta = np.zeros((tiles_y, tiles_x, 2), np.float64)
    delta[..., 0] = amplitude * np.sin(
        2 * np.pi * np.arange(tiles_x, dtype=np.float64) / 6.0)
    return fp.field2_mod.PageField(
        lane=None, stream_id=stream, page=0, plane=plane,
        delta_dots_xy=delta if supported else np.zeros_like(delta),
        support=(np.ones(_FIELD2_TILES_YX, np.float64) if supported
                 else np.zeros(_FIELD2_TILES_YX, np.float64)),
        poly_dots_xy=np.zeros_like(delta), degree=1 if supported else 0,
        tiles=((_TILE_OFFSET,) if supported else ()),
        median_delta_dots=float(amplitude), residual_rms_dots=0.25,
        lanes=(("capA", 0),), detail={"n_tiles_read": 12})



#: A field under a SECOND run dir, planted in the same memo: the product
#: must not carry it, and removing the accessor's run filter must fail.
_DECOY_RUN_DIR = "other-run"


#: The token `_field2_world` plants its fields under: the identity of
#: the pass that FILLED the memo (M2).  A product asked under it reads
#: `fitted_here` true; one asked under any other token, or under none,
#: reads false — which is the review's case, a second pass over the same
#: inputs whose own arms fitted nothing.
_FIRST_PASS: str = "pass-1"


def _field2_world(monkeypatch, planted: dict, cell_dots: int = 2,
                  pass_token: str = _FIRST_PASS):
    """A `_FakeRun` whose memo holds `planted` — fitted the way a pass
    fits, through `fit_pooled_page_field`, with only the reads stubbed —
    beside one decoy field fitted under a different run dir."""
    run = _FakeRun(tiles_yx=_FIELD2_TILES_YX)
    run.lanes = (_Field2Lane("capA", 0),)
    run.plane_fields = {(0, 0): _StandingField(17)}
    run.row = _Field2Row(cell_dots)
    decoy = _FakeRun(tiles_yx=_FIELD2_TILES_YX, run_dir=_DECOY_RUN_DIR)
    decoy.lanes, decoy.plane_fields = run.lanes, {}
    decoy.row = run.row
    bench = {(_DECOY_RUN_DIR, "M"): _planted_field("M", 1, 0.5),
             **{(str(run.run_dir), stream): field
                for stream, field in planted.items()}}

    monkeypatch.setattr(fp.field2_mod, "_MEMO", {})
    monkeypatch.setattr(fp.field2_mod, "_MEMO_ORDER", [])
    monkeypatch.setattr(fp.field2_mod, "_KEY_LOCKS", {})
    monkeypatch.setattr(
        fp.field2_mod, "_pooled_fit",
        lambda inputs, _certs, _lanes, stream_id, *_rest:
        bench[(str(inputs.run_dir), stream_id)])
    for owner in (decoy, run):
        for stream in ("M",) if owner is decoy else planted:
            fp.field2_mod.fit_pooled_page_field(
                owner, stream, 0, lanes=owner.lanes, tiles=8, seed=3,
                pass_token=pass_token)
    return run


def _field2_config(**over) -> AnalyzerConfig:
    """A config whose `field2` fit is the one `_field2_world` planted.

    The seed and the tile sample are part of the memo key, so a product
    reports a held field only under the configuration that would have
    fitted it (F12) — every test here that expects rows has to ask for
    the fit it planted.
    """
    fields = {"seed": 3, "knobs": {"field2_pooled_tiles": 8}}
    return AnalyzerConfig(**{**fields, **over})


def test_the_pass_writes_the_field2_fields_it_actually_fitted(monkeypatch,
                                                              tmp_path):
    """One row per (page, plane) in the memo, in the comparator's schema,
    each carrying the revision of the production field that stood."""
    run = _field2_world(monkeypatch, {"C": _planted_field("C", 0, 0.40),
                                      "Y": _planted_field("Y", 2, 0.90)})
    path = tmp_path / fp.FIELD2_PRODUCT_NAME
    product = fp.write_field2_product(
        run, _field2_config(workers=2,
                            arms=("subtract+committed",
                                  "subtract+field2+offset")), path,
        pass_token=_FIRST_PASS)

    assert path.exists() and json.loads(path.read_text()) == product
    assert product["seed"] == 3 and product["run_dir"] == str(run.run_dir)
    assert product["knobs"] == {"field2_pooled_tiles": 8}
    assert product["field2_arms"] == ["subtract+field2+offset"]
    assert "note" not in product
    assert all(row["fitted_here"] for row in product["fields"])

    # the rows ARE the memo's keys — read off the memo itself, not off
    # the accessor that produced them
    assert sorted((key.page, key.stream_id) for key in fp.field2_mod._MEMO) \
        == [(0, "C"), (0, "M"), (0, "Y")]        # the M is the decoy's
    assert [(row["page"], row["stream"], row["plane"])
            for row in product["fields"]] == [(0, "C", 0), (0, "Y", 2)]
    assert all(row["n_memo_entries"] == 1 for row in product["fields"])
    # each row's provenance is the FIT's, off its own key (F12)
    assert all(row["fit_seed"] == 3 for row in product["fields"])
    assert all(row["fit_knobs"]["tile_sample"] == 8
               and row["fit_knobs"]["pool"] == fp.field2_mod.POOL_WMEDIAN
               and row["fit_knobs"]["anchors"] == fp.field2_mod.
               ANCHORS_FURNITURE
               and row["fit_lane_ids"] == [["capA", 0]]
               for row in product["fields"])

    for row in product["fields"]:
        # what `compare.against_analyzer` reads off a row
        assert {"page", "stream", "field_dots_xy", "support",
                "sinusoid_x"} <= set(row)
        assert {"amplitude_dots", "period_tiles", "r_squared"} \
            <= set(row["sinusoid_x"])
        assert not row.get("fit_refused")
        assert np.asarray(row["field_dots_xy"]).shape \
            == _FIELD2_TILES_YX + (2,)
        assert np.asarray(row["support"]).shape == _FIELD2_TILES_YX
        # …and `field2.summary`'s own spelling, phase C's row
        assert {"anchors", "median_delta_dots", "residual_rms_dots",
                "degree", "sinusoid_y", "n_tiles_read"} <= set(row)
        assert row["pooled"] is True

    # the planted 6-tile wave is what the reported sinusoid says it is,
    # and the two products are pinned to ONE arithmetic: since the
    # 2026-09-13 review's F7 that is a shared truth-free module rather
    # than two copies of the source, so both are compared against
    # `harmonic` itself and not only against each other — a twin test
    # between two wrappers would pass however wrong the wrapped fit was.
    from analyzer import harmonic
    from analyzer.sweeps.field2_paper import sinusoid_fit
    profile = fp.field2_mod.column_profile(
        _planted_field("Y", 2, 0.90), axis=0)
    found = product["fields"][1]["sinusoid_x"]
    assert found["period_tiles"] == pytest.approx(6.0)
    assert found["fit"] == harmonic.FIT_NAME
    assert found == _field2_sinusoid_twin(profile)
    assert _field2_sinusoid_twin(profile) == sinusoid_fit(
        profile, fp.FIELD2_MM_PER_TILE)
    assert _field2_sinusoid_twin(profile) == harmonic.fit_sinusoid(
        profile, period_min_tiles=harmonic.PERIOD_MIN_TILES,
        period_step=harmonic.PERIOD_STEP_TILES,
        mm_per_tile=fp.FIELD2_MM_PER_TILE)

    # C's field stood at revision 17; nothing stood for Y
    assert [(row["production_field_known"], row["production_field_ordinal"])
            for row in product["fields"]] == [(True, 17), (False, None)]


def _field2_sinusoid_twin(profile):
    """The in-run sinusoid at the SWEEP's c2 mm-per-tile, so the twin
    comparison is over the one number the sweep hardcodes."""
    return fp._field2_sinusoid(profile, fp.FIELD2_MM_PER_TILE)


def test_the_product_carries_no_other_runs_fields(monkeypatch, tmp_path):
    """The memo is process-wide; the product is one run's.

    The decoy is fitted under a second run dir in the same memo, and the
    accessor filters on `id(inputs.run_dir)` the way the memo key does.
    Removing that filter puts the decoy's M plane in the product.
    """
    run = _field2_world(monkeypatch, {"C": _planted_field("C", 0, 0.40)})
    product = fp.field2_product(run, _field2_config(),
                                pass_token=_FIRST_PASS)
    assert [row["stream"] for row in product["fields"]] == ["C"]
    assert (0, 1) not in fp.field2_mod.fitted_pooled_fields(run)
    assert len(fp.field2_mod._MEMO) == 2       # both were really fitted


def test_the_product_carries_no_other_passs_fields(monkeypatch, tmp_path):
    """F12: the memo outlives a pass; the product is one pass's.

    The cache is keyed by RUN DIR, so a second `fixedpoint.run` over the
    same inputs — which the sweeps do, one per arm — found the first
    pass's fields there and published them under its own seed with an
    empty `field2_arms` and no note.  A held field now has to be the one
    THIS configuration would have fitted, and the memo is never cleared:
    the provenance was in the key all along.

    M2 closes the half the key could not: matching knobs are not
    authorship, so the pass's own token rides on the memo ENTRY and the
    product says `fitted_here` per row.
    """
    run = _field2_world(monkeypatch, {"C": _planted_field("C", 0, 0.40)})
    held = fp.field2_mod.fitted_pooled_fields(run)
    (one,), = held[(0, 0)],
    field, key, token = one
    assert field.stream_id == "C" and key.seed == 3 and key.tile_sample == 8
    assert token == _FIRST_PASS
    assert key.fit()["anchors"] == fp.field2_mod.ANCHORS_FURNITURE
    assert key.fit()["lane_ids"] == (("capA", 0),)

    # the review's own case: another pass, same inputs, seed 77, and a
    # battery with no `field2` arm in it at all
    other = fp.field2_product(run, AnalyzerConfig(
        seed=77, arms=("subtract+committed",)))
    assert other["fields"] == [] and other["field2_arms"] == []
    assert "fitted no pooled field2 field" in other["note"]

    # a knob that changes the arithmetic is enough on its own
    for knobs in ({"field2_pooled_tiles": 12},
                  {"field2_pooled_tiles": 8, "field2_pool": "wmean"},
                  {"field2_pooled_tiles": 8, "field2_bandwidth_tiles": 3.0}):
        assert fp.field2_product(run, _field2_config(knobs=knobs))["fields"] \
            == [], knobs

    # …and a pass whose knobs DO match but whose battery names no field2
    # arm says so rather than passing the rows off as its own measurement
    reader = fp.field2_product(run, _field2_config(
        arms=("subtract+committed",)), pass_token="pass-2")
    assert [row["stream"] for row in reader["fields"]] == ["C"]
    assert reader["field2_arms"] == []
    assert [row["fitted_here"] for row in reader["fields"]] == [False]
    assert "no row here was fitted by THIS pass" in reader["note"]

    # THE REVIEW'S CASE EXACTLY (M2): the second pass's knobs match and
    # its battery DOES name a field2 arm — it simply reached no target,
    # so `field_for` was never called and the memo entry is the first
    # pass's.  A populated `field2_arms` used to make that row silent.
    armed = fp.field2_product(run, _field2_config(
        arms=("subtract+field2+offset",)), pass_token="pass-2")
    assert armed["field2_arms"] == ["subtract+field2+offset"]
    assert [row["fitted_here"] for row in armed["fields"]] == [False]
    assert "no row here was fitted by THIS pass" in armed["note"]
    # and the memo was NOT cleared on the way
    assert len(fp.field2_mod._MEMO) == 2


def test_a_fit_that_stood_on_no_anchor_refuses_by_name(monkeypatch,
                                                       tmp_path):
    """A zero grid is not a field, and the comparator must skip it.

    `field_from_pooled` returns a `PageField` with an EMPTY `tiles` when
    no furniture anchor stood; published as a field it would score nan
    against production.  It carries phase C's own reason string instead,
    which `compare.against_analyzer` skips (`_empty_entry`).
    """
    from analyzer.sweeps import field2_paper
    run = _field2_world(monkeypatch,
                        {"C": _planted_field("C", 0, 0.40, supported=False),
                         "Y": _planted_field("Y", 2, 0.90)})
    product = fp.field2_product(run, _field2_config())
    refused, stood = product["fields"]
    assert refused["fit_refused"] == "no_furniture_anchors"
    assert "no_furniture_anchors" in inspect.getsource(field2_paper)
    assert "fit_refused" not in stood


def test_the_period_in_mm_is_this_runs_rung_not_a_hardcoded_c2(monkeypatch):
    """A c3 tile is 1.5x as wide, and `period_mm` says so.

    The sweep runs on one c2 corpus and spells the 2 (`MM_PER_TILE`); a
    ladder takes whatever rung it is given, so the in-run product reads
    `cell_dots_of(inputs.row)` and a c3 pass reports 8.128 mm/tile where
    a hardcoded c2 would report 5.419.
    """
    planted = {"C": _planted_field("C", 0, 0.40)}
    two = fp.field2_product(_field2_world(monkeypatch, planted, cell_dots=2),
                            _field2_config())
    three = fp.field2_product(_field2_world(monkeypatch, planted,
                                            cell_dots=3), _field2_config())
    assert two["mm_per_tile"] == pytest.approx(_FIELD2_MM_C2)
    assert three["mm_per_tile"] == pytest.approx(_FIELD2_MM_C3)
    assert fp.FIELD2_MM_PER_TILE == pytest.approx(_FIELD2_MM_C2)
    at_c2 = two["fields"][0]["sinusoid_x"]
    at_c3 = three["fields"][0]["sinusoid_x"]
    assert at_c2["period_tiles"] == at_c3["period_tiles"]
    assert at_c3["period_mm"] == pytest.approx(1.5 * at_c2["period_mm"])


def test_a_rerolled_field2_arm_is_named_in_the_battery(monkeypatch,
                                                       tmp_path):
    """W8 B8: `pure+field2` is placed in the RE-ROLL, never in `arms`.

    `everything+patch+pure` and `patch-then-pure` carry it that way, it
    reaches `field2.field_for` all the same, and a header that read
    `arms` alone under-reported the battery — and could call a pass that
    fitted nothing arm-less when it was not.
    """
    assert "pure+field2" in types_mod.PROFILES["patch-then-pure"][
        "reroll_only_arms"]
    run = _field2_world(monkeypatch, {})
    product = fp.write_field2_product(
        run, AnalyzerConfig(arms=("subtract+committed",),
                            reroll_only_arms=("pure+committed",
                                              "pure+field2")),
        tmp_path / fp.FIELD2_PRODUCT_NAME)
    assert product["field2_arms"] == ["pure+field2"]
    assert product["fields"] == []
    assert "the re-roll's included" in product["note"]


def test_every_pass_mints_its_own_token_and_hands_it_to_the_arms(monkeypatch):
    """M2: where the product's `fitted_here` comes from.

    One ordinal per `run` call, published in the header so a product
    written beside the ledger can name the pass, and carried into every
    key's knob bag where `field2.field_for` reads it.  It is stamped
    AFTER the operator's knobs, so it is provenance rather than a dial.
    """
    _stubbed_driver(monkeypatch, certify=set(), follow_ups={})
    keys = [(0, 0, 0, "C")]
    first = fp.run(_FakeRun(), keys, _pass_config()).header["pass_token"]
    second = fp.run(_FakeRun(), keys, _pass_config()).header["pass_token"]
    assert isinstance(first, int) and second == first + 1

    bare = _FakeRun()
    bare.plane_fields = {}
    config = AnalyzerConfig(knobs={"field2_pass_token": "forged"})
    assert fp._knobs_for(bare, config, keys[0], None, 7)[
        "field2_pass_token"] == 7
    assert fp._knobs_for(bare, config, keys[0], None)[
        "field2_pass_token"] is None


def test_a_pass_that_fitted_no_field2_says_so(monkeypatch, tmp_path):
    """No `field2` arm anywhere in the battery is no measurement — an
    empty list and a note, never a refit behind the pass's back."""
    run = _field2_world(monkeypatch, {})
    product = fp.write_field2_product(
        run, AnalyzerConfig(arms=("subtract+committed",)),
        tmp_path / fp.FIELD2_PRODUCT_NAME)
    assert product["fields"] == [] and product["field2_arms"] == []
    assert "fitted no pooled field2 field" in product["note"]
    assert (tmp_path / fp.FIELD2_PRODUCT_NAME).exists()


# ------------------------------- the streamed ledger (the memory wave)

def _streamed_world(monkeypatch, *, certify: set, follow_ups: dict,
                    on_key=None) -> None:
    """`_stubbed_driver` with a hook that fires INSIDE a key's work.

    The point of a streamed ledger is what is on disk while the pass is
    still running, so the tests need a door into the middle of one.
    """
    _stubbed_driver(monkeypatch, certify=certify, follow_ups=follow_ups)
    real = fp.blind_key

    def watched(inputs, certs, key, config, exposure, **kw):
        if on_key is not None:
            on_key(key)
        return real(inputs, certs, key, config, exposure, **kw)

    monkeypatch.setattr(fp, "blind_key", watched)


def _pass_config(**kw) -> AnalyzerConfig:
    base = dict(workers=1, max_generations=4, rungs=("L0",), rules=("sum",))
    base.update(kw)
    return AnalyzerConfig(**base)


def test_the_pass_streams_its_rows_and_keeps_none(monkeypatch, tmp_path):
    """Items 1 and 5: the header before generation 0, the rows as they
    fold, and `Ledger.rows` empty at the end.

    The 2026-09-10 pass was killed at 350 keys with NOTHING on disk: the
    out dir was created after `fp.run` returned and the rows were held
    until then — 15-32 GB of them on a 2,700-target pass.
    """
    from analyzer import ledger as ledger_mod

    first = [(0, 0, 0, "C"), (0, 0, 1, "C"), (0, 0, 2, "C")]
    second = (0, 1, 0, "C")
    path = tmp_path / "ledger.jsonl"
    seen: list[tuple] = []

    def watcher(key):
        seen.append((key, len(path.read_text("utf-8").splitlines())))

    _streamed_world(monkeypatch, certify={first[0], second},
                    follow_ups={first[0]: (second,)}, on_key=watcher)
    writer = ledger_mod.LedgerWriter(path)
    ledger = fp.run(_FakeRun(), first, _pass_config(), writer=writer)
    writer.finish(ledger.header)

    # the header stood before the first key, and generation 0's three
    # rows were on disk before generation 1's key was attempted
    assert seen[0][1] == 1 and [key for key, _lines in seen] == first + [second]
    assert seen[-1][1] == 4
    assert ledger.rows == []                       # the pass keeps none
    assert ledger.header["n_rows"] == 4
    assert ledger.header["n_certified"] == 2
    assert ledger.header["generations_run"] == 2
    assert set(ledger.certified) == {first[0], second}
    stats = ledger_mod.ReadStats()
    rows = list(ledger_mod.iter_rows_latest(path, stats=stats))
    assert [tuple(row[name] for name in ("page", "ty", "tx", "stream_id"))
            for row in rows] == first + [second]
    assert stats.superseded == 0 and stats.truncated_lines == 0
    assert ledger_mod.read_header(path)["n_rows"] == 4


def test_a_library_caller_without_a_writer_still_gets_its_rows(monkeypatch):
    """The controls and the small tests read `ledger.rows`; a pass with
    no writer is the one it always was."""
    keys = [(0, 0, 0, "C"), (0, 0, 1, "C")]
    _stubbed_driver(monkeypatch, certify={keys[0]}, follow_ups={})
    ledger = fp.run(_FakeRun(), keys, _pass_config())
    assert [row.key for row in ledger.rows] == keys
    assert ledger.header["n_rows"] == 2
    assert list(ledger.certified) == [keys[0]]


def test_a_re_attacked_key_appends_a_row_and_the_header_counts_keys(
        monkeypatch, tmp_path):
    """The W3 cascade re-attacks an attempted key; a streamed ledger
    cannot rewrite the row it already flushed, so it appends one."""
    from analyzer import ledger as ledger_mod

    first, second = (0, 0, 0, "C"), (0, 0, 1, "C")
    _stubbed_driver(monkeypatch, certify={first},
                    follow_ups={first: (second,)})
    path = tmp_path / "ledger.jsonl"
    writer = ledger_mod.LedgerWriter(path)
    ledger = fp.run(_FakeRun(), [first, second], _pass_config(),
                    writer=writer)
    writer.finish(ledger.header)

    assert len(list(ledger_mod.iter_rows(path))) == 3     # second, twice
    stats = ledger_mod.ReadStats()
    latest = list(ledger_mod.iter_rows_latest(path, stats=stats))
    assert [row["tx"] for row in latest] == [0, 1]
    assert [row["diag"]["attempts"] for row in latest] == [1, 2]
    assert stats.superseded == 1
    # the header counts KEYS, exactly as it did when a re-attack
    # replaced the row in memory
    assert ledger.header["n_rows"] == 2


def test_every_certificate_lands_in_the_mint_file_as_it_is_won(
        monkeypatch, tmp_path):
    """Item 2: the mint file is written a GENERATION before the rows.

    A row is final only when its whole generation has folded, and the
    pass this wave exists for died inside generation 0.  So the hook
    that writes `mints.jsonl` fires as each key returns, and the file it
    writes is an `export-facts` input on its own.
    """
    from analyzer import ledger as ledger_mod

    keys = [(0, 0, index, "C") for index in range(3)]
    lines: list[int] = []

    def watcher(_key):
        lines.append(len(
            (tmp_path / ledger_mod.MINTS_NAME).read_text("utf-8").splitlines()))

    _streamed_world(monkeypatch, certify={keys[0], keys[2]}, follow_ups={},
                    on_key=watcher)
    writer = ledger_mod.LedgerWriter(tmp_path / "ledger.jsonl")
    ledger = fp.run(_FakeRun(), keys, _pass_config(), writer=writer)
    writer.finish(ledger.header)

    # header, then one mint after key 0 and none after key 1 — the file
    # grew DURING the generation, not at its fold
    assert lines == [1, 2, 2]
    assert writer.n_mints == 2
    mints = list(ledger_mod.iter_rows(writer.mints_path))
    assert [(row["ty"], row["tx"], row["stream_id"]) for row in mints] \
        == [(0, 0, "C"), (0, 2, "C")]
    for row in mints:
        assert row["verdict"] == VERDICT_CERTIFIED
        assert row["certifying_rule"] == "sum"
        assert row["certifying_rung"] == "L0"
        assert row["generation"] == 0
        assert row["rungs"]["user_bits"] == [0, 0, 0, 0]


def test_the_mint_record_carries_the_certifying_rung_where_score_reads_it():
    """`mints.jsonl` answers the scorer's question too, so the mint file
    alone says everything the row would have about the certificate.

    The scorer takes the packed exit hard vector off a RUNG dict under
    `rungs[rule]` (`oracle.packed_hard`), never off the row, so the
    certifying rung rides the mint in the row's own spelling.
    """
    from analyzer import oracle as oracle_mod        # OFFLINE, a test may
    from analyzer.types import RungResult

    packed = bytes(range(8))
    work = {
        "certifying_rule": "sum", "certifying_rung": "L1",
        "certifying_arm": "subtract+committed", "seconds": 0.5,
        "user_bits": np.ones(4, np.uint8),
        "rungs": {"sum": [
            RungResult(rung="L0", verdict="open", n_iters=1,
                       unsat_at_exit=9, syndrome_ok=False,
                       posterior_summary={}, crc_consults_distinct=0,
                       user_bits=None, seconds=0.1, detail={}),
            RungResult(rung="L1", verdict=VERDICT_CERTIFIED, n_iters=2,
                       unsat_at_exit=0, syndrome_ok=True,
                       posterior_summary={}, crc_consults_distinct=1,
                       user_bits=np.ones(4, np.uint8), seconds=0.2,
                       detail={"hard_packed": packed})]}}
    record = fp.mint_record((0, 3, 4, "Y"), work, generation=2,
                            verdict=VERDICT_CERTIFIED)
    assert "hard_packed_b64" not in record       # never at the top level
    rung = record["rungs"]["sum"][0]
    assert [item["rung"] for item in record["rungs"]["sum"]] == ["L1"]
    assert rung["detail"]["hard_packed_b64"] == \
        base64.b64encode(packed).decode()
    assert oracle_mod.packed_hard(rung) == packed
    assert record["verdict"] == VERDICT_CERTIFIED
    assert record["certifying_arm"] == "subtract+committed"
    assert record["generation"] == 2
    assert list(record["rungs"]["user_bits"]) == [1, 1, 1, 1]



def test_the_driver_holds_no_default_evidence_any_more():
    """Item 5, grep-pinned: `out["default_evidence"]` held a full
    `Evidence` per lane — a 3,976-cell float64 vector each — and NOTHING
    read it.  The two occurrences were its own."""
    text = (PACKAGE / "fixedpoint.py").read_text("utf-8")
    assert "default_evidence" not in text


class _Work(dict):
    """A work dict that can be weak-referenced (a plain dict cannot)."""


def _alive_when_rows_fold(monkeypatch, tmp_path, *, workers: int
                          ) -> list[int]:
    """How many of a generation's work dicts are alive at each fold."""
    import weakref

    keys = [(0, 0, index, "C") for index in range(6)]
    refs: list = []


    def fake_blind_key(_inputs, _certs, _key, _config, _exposure, **_kw):
        out = _Work({"seconds": 0.0, "n_lanes": 1})
        refs.append(weakref.ref(out))
        return out

    monkeypatch.setattr(fp, "blind_key", fake_blind_key)
    monkeypatch.setattr(fp, "_retarget", lambda *_args: [])
    monkeypatch.setattr(fp.inputs_mod, "metadata_bit", lambda *_args: 0)

    alive: list[int] = []

    class _Counting:
        """A writer that counts the living work dicts as each row folds."""

        path = tmp_path / "ledger.jsonl"
        mints_path = tmp_path / "mints.jsonl"
        n_rows = n_mints = 0

        def start(self, _header): pass

        def mint(self, _record): pass

        def append(self, _row):
            alive.append(sum(1 for ref in refs if ref() is not None))

    fp.run(_FakeRun(), keys, _pass_config(workers=workers),
           writer=_Counting())
    return alive


def test_the_generation_batch_dies_as_its_rows_fold(monkeypatch, tmp_path):
    """Item 5, pinned on BEHAVIOUR: `results.pop` frees a work dict only
    if nothing else holds it, and at workers > 1 something did.

    A `Future` keeps its `_result` for as long as the list of futures
    does, so the whole generation stayed alive through the fold: measured
    with weakrefs 2026-09-13, workers=1 counted [6,5,4,3,2,1] living work
    dicts as the six rows folded and workers=4 counted [6,6,6,6,6,6].
    The drain empties each slot as it reads it.
    """
    serial = _alive_when_rows_fold(monkeypatch, tmp_path, workers=1)
    parallel = _alive_when_rows_fold(monkeypatch, tmp_path, workers=4)
    for alive in (serial, parallel):
        assert len(alive) == 6
        assert alive == sorted(alive, reverse=True), alive
        assert alive[-1] <= 2, alive          # the last row's own, at most
        assert alive[0] - alive[-1] >= 4, alive
    assert parallel[-1] <= serial[-1] + 1



# ------------------------------------------------ the checkpoint (item 3)

class _Clock:
    """A clock a test owns, for the only honest test of a timer."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_the_checkpoint_is_written_on_the_timer(monkeypatch, tmp_path):
    from analyzer import ledger as ledger_mod
    from analyzer import stopdoor as doors

    keys = [(0, 0, index, "C") for index in range(4)]
    clock = _Clock()
    checkpoint = doors.Checkpointer(tmp_path / doors.CHECKPOINT_NAME,
                                    minutes=30, clock=clock)

    def watcher(_key):
        clock.now += 31 * 60.0              # every key is half an hour

    _streamed_world(monkeypatch, certify={keys[1]}, follow_ups={},
                    on_key=watcher)
    writer = ledger_mod.LedgerWriter(tmp_path / "ledger.jsonl")
    ledger = fp.run(_FakeRun(), keys, _pass_config(), writer=writer,
                    checkpoint=checkpoint)
    writer.finish(ledger.header)

    record = json.loads(
        (tmp_path / doors.CHECKPOINT_NAME).read_text("utf-8"))
    assert checkpoint.n_written >= 3
    assert record["generation"] == 0
    assert record["keys"]["targets"] == 4
    # the FOLDED counts are still zero inside a generation; the live one
    # is `mints_written`, and the gap between them is exactly why the
    # mint file exists — the file says so in its own `note`
    assert record["keys"]["certified_folded"] == 0
    assert record["keys"]["retired_folded"] == 0
    assert record["keys"]["mints_written"] == 1
    assert record["keys"]["attempted"] == 4
    assert "mints_written" in record["keys"]["note"]


    assert record["exposure"]["bound_expected_false"] > 0
    assert record["config"]["seed"] == AnalyzerConfig().seed
    assert record["config"]["rungs"] == ["L0"]
    assert record["memory"]["peak_rss_bytes"] > 0
    assert "peak RSS" in record["memory"]["line"]
    assert "export-facts" in record["recovery"] and "--resume" in \
        record["recovery"]
    assert str(tmp_path) in record["ledger"] and record["mints"].endswith(
        ledger_mod.MINTS_NAME)


def test_a_checkpoint_of_zero_minutes_writes_nothing(monkeypatch, tmp_path):
    from analyzer import stopdoor as doors

    keys = [(0, 0, 0, "C")]
    clock = _Clock()
    checkpoint = doors.Checkpointer(tmp_path / doors.CHECKPOINT_NAME,
                                    minutes=0, clock=clock)
    _stubbed_driver(monkeypatch, certify=set(), follow_ups={})
    clock.now += 10_000.0
    fp.run(_FakeRun(), keys, _pass_config(), checkpoint=checkpoint)
    assert not (tmp_path / doors.CHECKPOINT_NAME).exists()
    assert checkpoint.enabled is False


def test_a_checkpoint_that_cannot_be_written_is_a_line_not_the_pass(
        tmp_path):
    """Every product of a running pass is guarded; this one too."""
    from analyzer import stopdoor as doors

    lines: list[str] = []
    checkpoint = doors.Checkpointer(tmp_path / "no-such-dir" / "c.json",
                                    minutes=1, emit=lines.append)
    monkey = checkpoint.path.parent
    monkey.mkdir()
    monkey.chmod(0o500)
    try:
        assert checkpoint.write({"generation": 0}, reason="test") is None
    finally:
        monkey.chmod(0o700)
    assert lines and lines[0].startswith("checkpoint FAILED")


# --------------------------------------------- the progress line (item 4)

def test_the_progress_lines_carry_the_mints_and_the_peak_rss(monkeypatch):
    """A tick every N keys and a line at every generation boundary, both
    saying how much memory the pass is holding."""
    first = [(0, 0, 0, "C"), (0, 0, 1, "C")]
    second = (0, 1, 0, "C")
    _stubbed_driver(monkeypatch, certify={first[0], second},
                    follow_ups={first[0]: (second,)})
    lines: list[str] = []
    fp.run(_FakeRun(), first, _pass_config(), progress=lines.append,
           progress_every=2)
    ticks = [line for line in lines if line.startswith("  ")]
    assert len(ticks) == 2                  # 2 of 2 in gen 0, 1 of 1 in gen 1
    assert "2/2 done, +1 certified (1 mints)" in ticks[0]
    assert "s/key" in ticks[0] and "peak RSS" in ticks[0]
    assert ticks[0].endswith(f"(last {first[1]})")
    boundaries = [line for line in lines if line.startswith("generation")]
    assert len(boundaries) == 4
    for line in boundaries:
        assert "peak RSS" in line
    assert fp.PROGRESS_EVERY == 50


def test_the_peak_rss_is_bytes_on_both_platforms(monkeypatch):
    from analyzer import stopdoor as doors

    monkeypatch.setattr(doors.sys, "platform", "darwin")
    on_mac = doors.peak_rss_bytes()
    monkeypatch.setattr(doors.sys, "platform", "linux")
    on_linux = doors.peak_rss_bytes()
    assert on_linux == on_mac * 1024        # ru_maxrss is KiB there
    assert on_mac > 1 << 20


def test_the_orderly_stop_writes_one_last_checkpoint(monkeypatch, tmp_path):
    """The file beside the ledger must describe the pass that was
    STOPPED, not the half hour before it."""
    import signal

    from analyzer import ledger as ledger_mod
    from analyzer import stopdoor as doors

    keys = [(0, 0, index, "C") for index in range(4)]
    clock = _Clock()
    checkpoint = doors.Checkpointer(tmp_path / doors.CHECKPOINT_NAME,
                                    minutes=30, clock=clock)

    def watcher(key):
        if key == keys[1]:
            signal.raise_signal(signal.SIGINT)

    _streamed_world(monkeypatch, certify=set(keys), follow_ups={},
                    on_key=watcher)
    writer = ledger_mod.LedgerWriter(tmp_path / "ledger.jsonl")
    saved = {signum: signal.getsignal(signum)
             for signum in doors.STOP_SIGNALS}
    try:
        ledger = fp.run(_FakeRun(), keys, _pass_config(),
                        progress=lambda _line: None, writer=writer,
                        checkpoint=checkpoint)
    finally:
        for signum, original in saved.items():
            signal.signal(signum, original)
    writer.finish(ledger.header)

    assert ledger.header["stop_reason"] == fp.STOP_INTERRUPTED
    record = json.loads(
        (tmp_path / doors.CHECKPOINT_NAME).read_text("utf-8"))
    assert record["reason"] == "stop"          # the timer never came due
    assert record["stop_requested"] is True
    assert record["keys"]["certified_folded"] == \
        ledger.header["n_certified"] == 2

    assert record["keys"]["mints_written"] == 2
    # and the two rows the pass DID fold are on disk, the two the door
    # turned away are not
    assert len(list(ledger_mod.iter_rows(writer.path))) == 2
    assert len(list(ledger_mod.iter_rows(writer.mints_path))) == 2
