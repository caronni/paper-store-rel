"""W2 — `analyzer.fixedpoint`: the driver, and the blindness it claims.

The first three tests are the ones that matter: the import-set test of
PLAN §0 (no blind module may reach `truth` or `oracle`), the AST pin on
`blind_key` (the whole decision path, named so it can be pinned), and the
`wrong` abort.  Everything after that is plumbing, and the sheet-I leg
drives the three residue tile-streams of the resume-3 run to a fixed
point.
"""

from __future__ import annotations

import ast
import base64
import inspect
import threading
from pathlib import Path

import numpy as np
import pytest

from analyzer import fixedpoint as fp
from analyzer.types import VERDICT_CERTIFIED, AnalyzerConfig

from ._analyzer_fixtures import i_census, i_inputs, needs_i_run

PACKAGE = Path(fp.__file__).resolve().parent

#: PLAN §0: these decide, so none of them may see the score column.
BLIND_MODULES = ("unmix", "calibrate", "combine", "ladder", "mother",
                 "frame", "sample", "arms", "residue", "inputs")
FORBIDDEN = ("truth", "oracle")


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                out.add(f"{module}.{alias.name}" if module else alias.name)
                out.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
    return out


@pytest.mark.parametrize("module", BLIND_MODULES)
def test_blind_modules_never_import_truth_or_oracle(module):
    names = _imported_names(PACKAGE / f"{module}.py")
    for banned in FORBIDDEN:
        assert banned not in names, (
            f"analyzer/{module}.py imports {banned!r}; DESIGN §0 says "
            f"truth is a SCORE COLUMN and may not reach a decision")
        assert f"analyzer.{banned}" not in names


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
    assert "subtract+smooth" in config.battery_for("Y")
    assert "subtract+smooth" not in config.battery_for("C")
    assert "subtract+word" in config.battery_for("C")
    assert "subtract+word" not in config.battery_for("Y")
    assert config.battery_for("Y")[0] == "subtract+offset"


def test_refused_arms_leave_the_battery():
    config = AnalyzerConfig(refused_arms=("subtract+field",))
    assert "subtract+field" not in config.battery_for("C")
    assert "subtract+field+offset" in config.battery_for("C")


def test_locked_set_survives_concurrent_adds():
    exposure = fp.shared_exposure()

    def worker(base: int) -> None:
        for index in range(500):
            exposure.consulted.add(bytes([base, index % 256, index // 256]))

    threads = [threading.Thread(target=worker, args=(base,))
               for base in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert exposure.distinct == 8 * 500
    assert exposure.expected_false == pytest.approx(4000 * 2.0 ** -32)


def test_shared_exposure_takes_a_bound():
    exposure = fp.shared_exposure(1e-9)
    assert exposure.bound_expected_false == 1e-9
    assert exposure.would_exceed(100) is True


def test_rung_dict_strips_the_hard_vector():
    from analyzer.types import RungResult
    result = RungResult(rung="L0", verdict="open", user_bits=None, n_iters=60,
                        unsat_at_exit=3, syndrome_ok=False,
                        posterior_summary={}, crc_consults_distinct=0,
                        seconds=0.5,
                        detail={"hard_packed": b"\x00" * 512, "mode": "sp"})
    out = fp._rung_dict(result)
    assert "hard_packed" not in out["detail"]
    assert out["detail"]["mode"] == "sp"


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
    assert stored["unsat_at_exit"] == 9 and stored["n_iters"] == 150


def test_keep_hard_is_on_by_default_in_the_driver():
    """The knob the ledger row depends on is not left to a caller."""
    source = (PACKAGE / "fixedpoint.py").read_text("utf-8")
    assert '"keep_hard": True' in source


# ------------------------------------------------------- the sheet-I leg

@needs_i_run
def test_sheet_i_residue_runs_to_a_fixed_point():
    """Q1.6: the battery + L0-L3 + L7 over the resume-3 run's residue."""
    run = i_inputs()
    rows = i_census()
    residue = [row for row in rows
               if row.covered and not row.certified_by_production]
    assert len(residue) == 3, [row.key for row in residue]
    config = AnalyzerConfig(workers=4, rules=("sum", "best"),
                            rungs=("L0", "L1", "L2", "L3", "L7"),
                            max_generations=8)
    ledger = fp.run(run, residue, config, census_rows=rows)

    assert [row.key for row in ledger.rows[:3]] == [row.key
                                                    for row in residue]
    certified = [row for row in ledger.rows
                 if row.verdict == VERDICT_CERTIFIED]
    print(f"\nQ1.6 sheet I: {len(certified)}/{len(ledger.rows)} certified "
          f"in {ledger.header['seconds']:.1f}s, exposure "
          f"{ledger.header['exposure_distinct']} distinct "
          f"(E[false] {ledger.header['exposure_expected_false']:.3g})")
    for row in ledger.rows:
        print(f"  {row.key} {row.verdict} gen={row.generation} "
              f"rule={row.certifying_rule} rung={row.certifying_rung} "
              f"lanes={row.diag.get('n_lanes')} "
              f"attempts={row.diag.get('attempts')}")
    # The run says `certified` or `open` and nothing else; whether those
    # three certificates are RIGHT is `analyzer score`'s answer, and
    # `test_analyzer_score.py` asks it on this very ledger.
    assert {row.verdict for row in ledger.rows} <= {VERDICT_CERTIFIED,
                                                    "certified_list", "open"}
    assert len(certified) == 3
    for row in ledger.rows:
        for rule, batch in row.rungs.items():
            if rule == "user_bits":
                continue
            assert any("hard_packed_b64" in item["detail"]
                       for item in batch), rule


@needs_i_run
def test_sheet_i_ledger_is_worker_count_independent_in_its_order():
    run = i_inputs()
    rows = i_census()
    residue = [row for row in rows
               if row.covered and not row.certified_by_production]
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


@needs_i_run
def test_sheet_i_metadata_bit_is_available_and_used():
    run = i_inputs()
    from analyzer import inputs as inputs_mod
    key = sorted(run.certificates)[0]
    bit = inputs_mod.metadata_bit(run, key)
    assert bit in (0, 1)
    assert int(np.asarray(run.certificates[key].user_bits)[0]) == bit


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
