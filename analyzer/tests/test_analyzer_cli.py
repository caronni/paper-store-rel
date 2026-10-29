"""W2 — `analyzer.cli`: the operator's door (PLAN §5).

Parser shape first (a flag that silently does not exist is the classic
CLI bug), then one real `census` run against a decoded run dir, which
is also the smoke test PLAN §3 asks for.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from analyzer import cli
from analyzer import types as types_mod

from ._analyzer_fixtures import RESIDUE_WITHHELD, needs_sim, residue_run_dir

#: A run command's two required flags, for the parser-only tests.
RUN = ("--run-dir", "/tmp/x", "--out", "/tmp/o")


def test_every_subcommand_of_plan_5_exists():
    parser = cli.build_parser()
    actions = [action for action in parser._actions
               if getattr(action, "choices", None)
               and "census" in action.choices]
    assert actions, "no subparser action"
    assert set(actions[0].choices) == {"census", "read", "ladder",
                                       "controls", "close", "mirror",
                                       "export-facts", "report",
                                       "emit-plane", "plane-view-decode",
                                       "union-base", "score"}
    assert set(cli.COMMANDS) == set(actions[0].choices)


def test_format_ref_is_on_every_subcommand():
    """PLAN §6: sheet J is unreadable without `--format-ref`, so the flag
    is on every door, not only the ones that load a run."""
    parser = cli.build_parser()
    for command, argv in (
            ("score", ["--ledger", "/tmp/l.jsonl", "--payload", "/tmp/p",
                       "--out", "/tmp/o"]),
            ("census", [*RUN]),
            ("read", [*RUN]),
            ("ladder", [*RUN]),
            ("controls", [*RUN]),
            ("close", [*RUN]),
            ("mirror", ["--src-run-dir", "/tmp/x", "--out", "/tmp/y"]),
            ("export-facts", ["--snapshot", "/tmp/f.npz", "--ledger",
                              "/tmp/l.jsonl", "--out", "/tmp/n.npz"]),
            ("report", ["/tmp/ledger.jsonl"])):
        args = parser.parse_args([command, *argv])
        assert hasattr(args, "format_ref"), f"{command} has no --format-ref"
        assert args.format_ref is None
        args = parser.parse_args([command, *argv, "--format-ref", "L:x@1x1"])
        assert args.format_ref == "L:x@1x1"


@pytest.mark.parametrize("flag", [
    "--run-dir", "--out", "--seed", "--workers",
    "--cover-fraction", "--halo-cells"])
def test_the_common_flags_are_on_every_run_command(flag):
    parser = cli.build_parser()
    for command in ("census", "read", "ladder", "controls", "close"):
        args = parser.parse_args([command, *RUN])
        name = flag.lstrip("-").replace("-", "_")
        assert hasattr(args, name), f"{command} has no {flag}"


@pytest.mark.parametrize("command", ["census", "read", "ladder", "controls",
                                     "close"])
def test_a_run_command_without_out_refuses(command):
    """No default artefact directory (2026-10-09): `--out` is required."""
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([command, "--run-dir", "/tmp/x"])


@pytest.mark.parametrize("command", ["census", "read", "ladder", "controls",
                                     "close", "export-facts"])
def test_no_run_command_takes_a_payload(command):
    """RULED 2026-09-04: `--gt-dir` and `--payload` live on `score` only."""
    parser = cli.build_parser()
    argv = (["--snapshot", "/tmp/f.npz", "--ledger", "/tmp/l.jsonl",
             "--out", "/tmp/n.npz"] if command == "export-facts"
            else [*RUN])
    args = parser.parse_args([command, *argv])
    assert not hasattr(args, "gt_dir"), f"{command} still takes --gt-dir"
    assert not hasattr(args, "payload"), f"{command} still takes --payload"
    for flag in ("--gt-dir", "--payload"):
        with pytest.raises(SystemExit):
            parser.parse_args([command, *argv, flag, "/tmp/p"])


def test_score_is_the_one_door_with_a_payload():
    args = cli.build_parser().parse_args(
        ["score", "--ledger", "/tmp/a.jsonl", "--ledger", "/tmp/b.jsonl",
         "--payload", "/tmp/payload.bin", "--gt-dir", "/tmp/gen",
         "--run-dir", "/tmp/run", "--out", "/tmp/score", "--limit", "5"])
    assert [str(path) for path in args.ledgers] == ["/tmp/a.jsonl",
                                                    "/tmp/b.jsonl"]
    assert str(args.payload) == "/tmp/payload.bin"
    assert str(args.gt_dir) == "/tmp/gen" and args.limit == 5


def test_union_base_carries_its_three_doors():
    args = cli.build_parser().parse_args(
        ["union-base", "--run-dir", "/tmp/base", "--facts", "/tmp/f.npz",
         "--out", "/tmp/u", "--no-verify-facts"])
    assert str(args.run_dir) == "/tmp/base"
    assert str(args.facts) == "/tmp/f.npz"
    assert args.verify_facts is False
    assert cli.build_parser().parse_args(
        ["union-base", "--run-dir", "/tmp/base", "--facts", "/tmp/f.npz",
         "--out", "/tmp/u"]).verify_facts is True


def test_ladder_carries_the_pass_flags():
    args = cli.build_parser().parse_args(
        ["ladder", *RUN, "--targets", "band:dead",
         "--arms", "subtract+offset,raw+committed",
         "--rules", "sum,best", "--rungs", "L0,L7", "--fixed-point",
         "--workers", "8", "--seed", "5"])
    assert args.targets == "band:dead" and args.fixed_point is True
    config = cli._config(args)
    assert config.arms == ("subtract+offset", "raw+committed")
    assert config.rules == ("sum", "best")
    assert config.rungs == ("L0", "L7")
    assert config.workers == 8 and config.seed == 5
    assert config.max_generations == 8         # --fixed-point opens it


def test_without_fixed_point_the_pass_is_one_generation():
    args = cli.build_parser().parse_args(["ladder", *RUN])
    assert cli._config(args).max_generations == 1


def _cap(*flags: str) -> int:
    args = cli.build_parser().parse_args(
        ["ladder", *RUN, *flags])
    return cli._config(args).max_generations


def test_the_generation_cap_and_the_fixed_point_are_orthogonal():
    """Ruling R1 (2026-09-06): `--max-generations N` works ON ITS OWN.

    It used to be discarded unless `--fixed-point` came with it, which
    is how the W8 smoke ran two `--max-generations 2` passes as single
    generations without a word (APPROACHES §6.5).
    """
    assert _cap() == 1                                   # neither flag
    assert _cap("--max-generations", "3") == 3           # the cap alone
    assert _cap("--fixed-point") == cli.DEFAULT_MAX_GENERATIONS
    assert _cap("--fixed-point", "--max-generations", "2") == 2
    # the cap BOUNDS the convergence in both directions, above the
    # default included: nothing here is a ceiling on what was spelled
    assert _cap("--fixed-point", "--max-generations", "20") == 20


def test_the_default_cap_is_the_librarys_own():
    assert cli.DEFAULT_MAX_GENERATIONS == \
        types_mod.AnalyzerConfig().max_generations


def test_a_cap_below_one_is_refused_not_run_as_zero_generations(capsys):
    args = cli.build_parser().parse_args(
        ["ladder", *RUN, "--max-generations", "0"])
    with pytest.raises(SystemExit) as caught:
        cli._config(args)
    assert caught.value.code == cli.EXIT_WRONG
    assert "GENERATIONS REFUSED" in capsys.readouterr().err


def test_controls_carries_every_withhold_door():
    args = cli.build_parser().parse_args(
        ["controls", *RUN, "--parity", "50",
         "--withhold-run-mints"])
    assert args.parity == 50 and args.withhold_run_mints is True
    args = cli.build_parser().parse_args(
        ["controls", *RUN, "--withhold-source",
         "tiles/planek150,tiles/swim150"])
    assert cli._list(args.withhold_source, ()) == ("tiles/planek150",
                                                   "tiles/swim150")
    args = cli.build_parser().parse_args(
        ["controls", *RUN, "--holdout-stratified",
         "Y:tiles/planek150=60,C:tiles/local150=20"])
    assert args.holdout_stratified == (
        "Y:tiles/planek150=60,C:tiles/local150=20")


def test_halo_override_applies_to_every_stream():
    args = cli.build_parser().parse_args(
        ["ladder", *RUN, "--halo-cells", "24"])
    assert cli._config(args).halo_cells == {"C": 24, "M": 24, "Y": 24}


def test_list_falls_back_to_the_default():
    assert cli._list(None, ("a", "b")) == ("a", "b")
    assert cli._list("x, y ,", ("a",)) == ("x", "y")


# --------------------------------------------------- the knob door (W8 B1)

def test_knob_values_parse_as_json_then_string():
    assert cli.parse_knob("branches=state") == ("branches", "state")
    assert cli.parse_knob("ctx_state=true") == ("ctx_state", True)
    assert cli.parse_knob("patch_shrinkage=0.01") == ("patch_shrinkage", 0.01)
    assert cli.parse_knob("patch_min_labels_per_state=600") == (
        "patch_min_labels_per_state", 600)
    assert cli.parse_knob("patch_channels=rgb") == ("patch_channels", "rgb")
    assert cli.parse_knob('L2=[{"mode": "damped", "iters": 300}]') == (
        "L2", [{"mode": "damped", "iters": 300}])
    assert cli.parse_knob("a=b=c") == ("a", "b=c")
    with pytest.raises(cli.KnobError):
        cli.parse_knob("no_equals_sign")
    parser = cli.build_parser()
    for command, argv in (("ladder", [*RUN]),
                          ("read", [*RUN]),
                          ("controls", [*RUN]),
                          ("score", ["--ledger", "/tmp/l.jsonl", "--payload",
                                     "/tmp/p", "--out", "/tmp/o"])):
        args = parser.parse_args([command, *argv, "--knob", "branches=state",
                                  "--knob", "patch_samples_per_cell=16"])
        config = cli._config(args)
        assert config.knobs["branches"] == "state"
        assert config.knobs["patch_samples_per_cell"] == 16
        assert config.knobs_from == "cli"
    # a knob lands AFTER the profile and the operator's value wins
    args = parser.parse_args(["ladder", *RUN, "--profile",
                              "split-branches", "--knob", "branches=state"])
    config = cli._config(args)
    assert config.knobs["branches"] == "state"
    assert config.knobs["starved_fallback"] is False      # the profile's
    assert config.knobs_from == "profile:split-branches+cli"
    plain = cli._config(parser.parse_args(
        ["ladder", *RUN, "--profile", "split-branches"]))
    assert plain.knobs_from == "profile:split-branches"
    assert plain.knobs["branches"] == "subtract"


@pytest.mark.parametrize("name", cli.RESERVED_KNOBS)
def test_reserved_knob_names_are_refused(name, capsys):
    with pytest.raises(cli.KnobError):
        cli.parse_knob(f"{name}=1")
    args = cli.build_parser().parse_args(
        ["ladder", *RUN, "--knob", f"{name}=1"])
    with pytest.raises(SystemExit) as exit_info:
        cli._config(args)
    assert exit_info.value.code == cli.EXIT_WRONG
    assert "KNOB REFUSED" in capsys.readouterr().err
    assert set(cli.RESERVED_KNOBS) == {
        "pseudo_labels", "refit", "sibling_state", "disagree", "ctx_offsets",
        "ctx_state_adopted", "state_weighted"}
    # ONE tuple: the CLI's parse-time refusal and `blind_key`'s own read
    # the same names (review 2026-09-06 — they used to be two copies).
    assert cli.RESERVED_KNOBS is types_mod.RESERVED_KNOBS


def test_a_malformed_patch_knob_is_refused_at_the_cli(capsys):
    args = cli.build_parser().parse_args(
        ["ladder", *RUN, "--knob", "patch_channels=cmyk"])
    with pytest.raises(SystemExit) as exit_info:
        cli._config(args)
    assert exit_info.value.code == cli.EXIT_WRONG
    assert "KNOB REFUSED" in capsys.readouterr().err
    good = cli._config(cli.build_parser().parse_args(
        ["ladder", *RUN, "--knob", "patch_channels=rgb",
         "--knob", "patch_samples_per_cell=16"]))
    assert good.knobs == {"patch_channels": "rgb", "patch_samples_per_cell": 16}


def test_score_refuses_a_config_carrying_pseudo_labels_or_refit():
    from analyzer import score as score_mod
    from analyzer.types import AnalyzerConfig
    for name in ("pseudo_labels", "refit"):
        with pytest.raises(ValueError):
            score_mod.evidence_for_row(None, {}, (0, 0, 0, "C"), None,
                                       AnalyzerConfig(knobs={name: object()}))


def test_main_pins_blas_threads_before_the_first_numpy_import():
    """APPROACHES §4.0 ruling 12: the pin precedes the `cli` import."""
    from pathlib import Path
    text = Path(cli.__file__).with_name("__main__.py").read_text("utf-8")
    pin = text.index("os.environ.setdefault")
    assert 0 < text.index("VECLIB_MAXIMUM_THREADS") < text.index(
        "from .cli import main")
    assert pin < text.index("from .cli import main")
    for name in ("VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS",
                 "OMP_NUM_THREADS"):
        assert name in text
    assert "import numpy" not in text


# ------------------------------------- the in-run `field2.json` (A2)

def test_the_field2_product_is_a_product_never_the_pass():
    """A diagnostic written mid-sequence may not cost a ladder its own
    outputs (the stop door's rule, `stopdoor.interrupt_products`).

    `field2.json` goes out between `ledger.jsonl`/`close.json` and
    `ledger.md`, the maps and the summary, so an exception escaping it
    would lose a multi-hour pass all three.  It is caught, printed and
    moved past, exactly like the close and the export.
    """
    tree = ast.parse(Path(cli.__file__).read_text("utf-8"))
    function = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "_pass")

    def calls_the_writer(node) -> bool:
        return any(isinstance(item, ast.Attribute)
                   and item.attr == "write_field2_product"
                   for item in ast.walk(node))

    guards = [node for node in ast.walk(function)
              if isinstance(node, ast.Try)
              and any(calls_the_writer(item) for item in node.body)]
    assert len(guards) == 1, "the field2 write is not inside exactly one try"
    handlers = guards[0].handlers
    assert [ast.unparse(one.type) for one in handlers] == ["Exception"]
    assert not [node for one in handlers for node in ast.walk(one)
                if isinstance(node, ast.Raise)], "the handler re-raises"
    # nothing else in `_pass` calls the writer outside that guard
    assert sum(1 for node in ast.walk(function)
               if isinstance(node, ast.Attribute)
               and node.attr == "write_field2_product") == 1


# --------------------------------------------------------- the smoke run

@needs_sim
def test_census_smoke_on_a_residue(tmp_path, capsys):
    """The colour sim's run with `RESIDUE_WITHHELD` taken out (TIER S):
    the residue is that set, and the 288 that remain still span K."""
    code = cli.main([
        "census", "--run-dir", str(residue_run_dir()),
        "--out", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr().out
    print(captured)
    assert f"residue {len(RESIDUE_WITHHELD)}" in captured
    assert (tmp_path / "census.jsonl").exists()
    ranks = json.loads((tmp_path / "census-rank.json").read_text("utf-8"))
    assert ranks["rank_report"] == ranks["rank_recomputed"] == 78
    assert ranks["agree"] is True


def test_report_re_renders_a_ledger(tmp_path):
    from analyzer import ledger as ledger_mod
    from .test_analyzer_ledger import make_row
    from analyzer.types import VERDICT_CERTIFIED
    path = tmp_path / "l.jsonl"
    ledger_mod.write_rows(
        path, [make_row(0, 0, rules=("sum",), verdict=VERDICT_CERTIFIED,
                        rungs_by_rule={"sum": [("L0", VERDICT_CERTIFIED)]},
                        certifying=("sum", "L0"))],
        {"rules": ["sum"], "rungs": ["L0"]})
    assert cli.main(["report", str(path), "--out", str(tmp_path)]) == 0
    assert "Order-free union: 1" in (
        tmp_path / "summary.md").read_text("utf-8")


def test_controls_takes_a_target_spec_in_the_same_grammar(tmp_path):
    """W8 B3 (K1): the controls can be pointed at one regime.  It is the
    `read`/`ladder` grammar, one spelling — and the help says what the
    operator must know, that the controls draw from CERTIFIED rows."""
    parser = cli.build_parser()
    args = parser.parse_args(["controls", *RUN,
                              "--targets", "band:dead"])
    assert args.targets == "band:dead"
    assert parser.parse_args(["controls", *RUN]).targets \
        is None

    class _Row:
        def __init__(self, key, band, certified):
            self.key = key
            self.page, self.ty, self.tx, self.stream_id = key
            self.band = band
            self.covered = True
            self.certified_by_production = certified

    listed = tmp_path / "keys.list"
    listed.write_text("# a comment\n0,12,30,C\n0,13,30,C\n", "utf-8")
    rows = [_Row((0, 12, 30, "C"), "dead", True),
            _Row((0, 13, 30, "C"), "dead", False),
            _Row((0, 14, 12, "C"), "live", True)]
    picked = cli._targets(rows, f"list {listed}")
    assert [row.key for row in picked] == [(0, 12, 30, "C"),
                                           (0, 13, 30, "C")]
    # ... and a residue spec keeps only the open rows, which is exactly
    # what a control cannot draw a donor from
    assert [row.key for row in cli._targets(rows, "band:dead")] == \
        [(0, 13, 30, "C")]


# ------------------------------------------- precedence and flags (W8 B5)

def test_ctx_mode_and_no_reroll_reach_the_config():
    """The two config fields that had no flag (README §7's own list)."""
    parser = cli.build_parser()
    plain = cli._config(parser.parse_args(["ladder", *RUN]))
    assert plain.ctx_mode == "production" and plain.reroll is True
    args = parser.parse_args(["ladder", *RUN,
                              "--ctx-mode", "local5", "--no-reroll"])
    config = cli._config(args)
    assert config.ctx_mode == "local5" and config.reroll is False
    # every mode the calibration knows is spellable, and nothing else is
    from analyzer.calibrate import CTX_MODES
    for mode in CTX_MODES:
        got = cli._config(parser.parse_args(
            ["ladder", *RUN, "--ctx-mode", mode]))
        assert got.ctx_mode == mode
    with pytest.raises(SystemExit):
        parser.parse_args(["ladder", *RUN,
                           "--ctx-mode", "telepathy"])
    # they are on `controls` and `read` too, so a control can be run at
    # the configuration it is controlling
    for command in ("read", "controls"):
        got = cli._config(parser.parse_args(
            [command, *RUN, "--ctx-mode", "none",
             "--no-reroll"]))
        assert got.ctx_mode == "none" and got.reroll is False


def test_explicit_arms_win_over_a_profile_and_the_header_says_so():
    """W8 B5 (APPROACHES §4.0 ruling 5): a profile supplies what the
    operator did not say.  Before this, `--profile patch --arms X` ran
    the profile's three arms and said nothing about it."""
    from types import SimpleNamespace
    from analyzer import fixedpoint as fp
    from analyzer.types import Exposure, PROFILES
    parser = cli.build_parser()
    profile = cli._config(parser.parse_args(
        ["ladder", *RUN, "--profile", "patch"]))
    assert profile.arms == PROFILES["patch"]["arms"]
    assert profile.knobs_from == "profile:patch"
    isolated = cli._config(parser.parse_args(
        ["ladder", *RUN, "--profile", "patch",
         "--arms", "patch+offset", "--rules", "sum", "--rungs", "L0,L1",
         "--halo-cells", "16", "--ctx-mode", "none", "--no-reroll"]))
    assert isolated.arms == ("patch+offset",)
    assert isolated.rules == ("sum",) and isolated.rungs == ("L0", "L1")
    assert isolated.halo_cells == {"C": 16, "M": 16, "Y": 16}
    assert isolated.ctx_mode == "none" and isolated.reroll is False
    # ... and what the operator did NOT say still comes from the profile
    assert isolated.knobs == PROFILES["patch"]["knobs"]
    assert isolated.knobs_from == "profile:patch+cli"
    # the ledger header carries both halves, so a run is reproducible
    # from its own first line
    inputs = SimpleNamespace(format_ref="L:x@1x1", run_dir="/tmp/x",
                             captures=(), provenance={})
    header = fp._header(inputs, isolated, Exposure(), 1)
    assert header["arms"] == ["patch+offset"]
    assert header["ctx_mode"] == "none" and header["reroll"] is False
    assert header["halo_cells"] == {"C": 16, "M": 16, "Y": 16}
    assert header["knobs_from"] == "profile:patch+cli"
    assert header["knobs"]["branches"] == "state"


def test_a_malformed_pure_knob_is_refused_at_the_cli(capsys):
    """W8 B5+: the pure path's knobs are checked at the same door the
    patch family's are, before a run dir is loaded."""
    args = cli.build_parser().parse_args(
        ["ladder", *RUN, "--knob", "pure_error_floor=0.9"])
    with pytest.raises(SystemExit) as exit_info:
        cli._config(args)
    assert exit_info.value.code == cli.EXIT_WRONG
    assert "KNOB REFUSED" in capsys.readouterr().err
    good = cli._config(cli.build_parser().parse_args(
        ["ladder", *RUN, "--knob", "calibration=pure",
         "--knob", "patch_train_scope=local5",
         "--knob", "patch_samples_per_cell=16"]))
    assert good.knobs["calibration"] == "pure"
    assert good.knobs["patch_train_scope"] == "local5"
    assert good.knobs["patch_samples_per_cell"] == 16


def test_a_placed_arm_is_reachable_from_the_command_line_and_beats_a_profile():
    """W8 B5: `--reroll-only-arms` is the one-pass door to B8's placement.

    B8 gave `AnalyzerConfig` the field and two profiles that set it, so
    placing an arm behind a battery meant writing a profile.  The flag
    places any arm, obeys the same precedence rule as every other
    explicit flag, and the header records it — a pass that carries the
    pure path behind the patch battery says so on its own first line.
    """
    from types import SimpleNamespace
    from analyzer import fixedpoint as fp
    from analyzer.types import Exposure, PROFILES
    parser = cli.build_parser()
    placed = cli._config(parser.parse_args(
        ["ladder", *RUN, "--profile", "patch",
         "--reroll-only-arms", "pure+committed,pure+field2"]))
    assert placed.reroll_only_arms == ("pure+committed", "pure+field2")
    # a PLACED arm is not a selection candidate: the battery is unchanged
    assert placed.battery_for("C") == PROFILES["patch"]["arms"]
    assert placed.reroll_battery_for("C") == ("pure+committed", "pure+field2")
    assert placed.knobs_from == "profile:patch+cli"
    # explicit beats the profile that already names placed arms
    over = cli._config(parser.parse_args(
        ["ladder", *RUN, "--profile", "patch-then-pure",
         "--reroll-only-arms", "mixture+offset"]))
    assert PROFILES["patch-then-pure"]["reroll_only_arms"] != ("mixture+offset",)
    assert over.reroll_only_arms == ("mixture+offset",)
    inputs = SimpleNamespace(format_ref="L:x@1x1", run_dir="/tmp/x",
                             captures=(), provenance={})
    header = fp._header(inputs, placed, Exposure(), 1)
    assert header["reroll_only_arms"] == ["pure+committed", "pure+field2"]


@pytest.mark.parametrize("flag,value,word", [
    ("--arms", "nonsense+offset", "unmix mode"),
    ("--arms", "patch+nowhere", "registration arm"),
    ("--arms", "patch", "<unmix>+<register>"),
    ("--reroll-only-arms", "pure+nowhere", "registration arm"),
    ("--rules", "platt-stat", "unknown rule"),
    ("--rungs", "L0,L9", "unknown rung"),
])
def test_a_misspelled_arm_rule_or_rung_is_refused_before_the_run_dir(
        flag, value, word, capsys):
    """W8 B5: every one of these names used to be checked deep inside a
    pass — an arm at the first `evidence_for`, a rung inside a worker at
    the first key, a rule at the first `combine` — so a typo cost a
    fourteen-worker pass its whole run before anyone saw it."""
    args = cli.build_parser().parse_args(
        ["ladder", *RUN, flag, value])
    with pytest.raises(SystemExit) as exit_info:
        cli._config(args)
    assert exit_info.value.code == cli.EXIT_WRONG
    err = capsys.readouterr().err
    assert "NAME REFUSED" in err and word in err


def test_the_name_check_accepts_every_profile_and_every_rung_the_ladder_has():
    """The refusal above must not refuse anything real: every profile as
    built, and every name in `types.KNOWN_RUNGS`, goes through."""
    from analyzer.types import KNOWN_RUNGS, PROFILES
    parser = cli.build_parser()
    for name in PROFILES:
        for command in ("ladder", "read", "controls"):
            cli._config(parser.parse_args(
                [command, *RUN, "--profile", name]))
    got = cli._config(parser.parse_args(
        ["ladder", *RUN, "--rungs", ",".join(KNOWN_RUNGS)]))
    assert got.rungs == KNOWN_RUNGS
    # `read` passes rungs=() as an override — an empty ladder is legal
    assert cli._config(parser.parse_args(
        ["read", *RUN]), rungs=(), rules=("sum",)).rungs == ()


def test_every_rung_the_ladder_dispatches_is_spellable():
    """`KNOWN_RUNGS` is the CLI's whole knowledge of the name space, so it
    must not drift from `ladder._run_rungs`' own if-chain.  Read the
    dispatch source and require every literal it compares against."""
    import ast
    import inspect
    from analyzer import ladder as ladder_mod
    from analyzer.types import KNOWN_RUNGS
    tree = ast.parse(inspect.getsource(ladder_mod._run_rungs))
    dispatched: set[str] = set()
    for node in ast.walk(tree):        # `name == "L4"` AND `name in (...)`
        if not (isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Name)
                and node.left.id == "name"):
            continue
        for side in node.comparators:
            elements = side.elts if isinstance(side, ast.Tuple) else [side]
            dispatched |= {item.value for item in elements
                           if isinstance(item, ast.Constant)
                           and isinstance(item.value, str)}
    # both spellings are in the chain today (L0/L1 and L5/L6 ride an
    # `in`, the rest an `==`); finding neither means the harvester has
    # rotted, which is itself the failure
    assert {"L0", "L4", "L3f"} <= dispatched, sorted(dispatched)
    assert dispatched <= set(KNOWN_RUNGS), sorted(dispatched - set(KNOWN_RUNGS))


# ------------------- the streamed ledger at the CLI (the memory wave)

def test_the_pass_flags_carry_the_checkpoint_door():
    args = cli.build_parser().parse_args(
        ["ladder", *RUN, "--checkpoint-minutes", "5"])
    assert args.checkpoint_minutes == 5.0
    default = cli.build_parser().parse_args(["ladder", *RUN])
    assert default.checkpoint_minutes == 30.0        # the wave's number
    assert default.progress_every == 50


def _stub_run():
    from analyzer.tests.test_analyzer_progress import _FakeRun
    return _FakeRun()


def _stubbed_pass(monkeypatch, tmp_path, *, certify, keys, on_key=None):


    """`ladder` end to end with every decision stubbed but the plumbing.

    What is under test is the ORDER the CLI does things in — the out
    dir and the ledger header before the first key, the report read back
    off the file afterwards — so the pass itself is the synthetic one
    the driver tests use.
    """
    from analyzer import fixedpoint as fp
    from analyzer.tests.test_analyzer_progress import _FakeRun, _stubbed_driver

    _stubbed_driver(monkeypatch, certify=certify, follow_ups={})
    if on_key is not None:                  # AFTER the stub, never before
        stub = fp.blind_key
        monkeypatch.setattr(
            fp, "blind_key",
            lambda *args, **kw: (on_key(args[2]), stub(*args, **kw))[1])
    monkeypatch.setattr(cli, "_load", lambda _args: _FakeRun())

    monkeypatch.setattr(cli, "_census", lambda _run, _args: [])
    monkeypatch.setattr(cli, "_targets", lambda _rows, _spec: list(keys))
    monkeypatch.setattr(cli.close_mod, "close",
                        lambda _run, certs, **_kw: {
                            "status": "short", "verified": False,
                            "n_certificates": len(certs),
                            "n_from_analyzer": len(certs),
                            "payload_path": None})
    monkeypatch.setattr(fp, "write_field2_product",
                        lambda *_args, **_kw: {"fields": []})
    return cli.main(["ladder", "--run-dir", "x", "--out", str(tmp_path),
                     "--no-maps", "--workers", "1", "--rungs", "L0",
                     "--rules", "sum", "--checkpoint-minutes", "0"])


def test_the_ladder_streams_its_ledger_and_its_mints(monkeypatch, tmp_path,
                                                     capsys):
    from analyzer import fixedpoint as fp
    from analyzer import ledger as ledger_mod


    keys = [(0, 0, 0, "C"), (0, 0, 1, "C"), (0, 0, 2, "C")]
    assert _stubbed_pass(monkeypatch, tmp_path,
                         certify={keys[0], keys[2]}, keys=keys) == 0
    captured = capsys.readouterr()
    assert "There is no --resume" in captured.err
    assert "mints" in captured.err

    stats = ledger_mod.ReadStats()
    rows = list(ledger_mod.iter_rows_latest(tmp_path / "ledger.jsonl",
                                            stats=stats))
    assert len(rows) == 3 and stats.truncated_lines == 0
    header = ledger_mod.read_header(tmp_path / "ledger.jsonl")
    assert header["n_rows"] == 3 and header["partial"] is False
    assert header["stop_reason"] == fp.STOP_FIXED_POINT
    mints = list(ledger_mod.iter_rows(tmp_path / ledger_mod.MINTS_NAME))
    assert [(row["ty"], row["tx"]) for row in mints] == [(0, 0), (0, 2)]
    # the summary counted the rows it read back off the FILE (the driver
    # handed it none), and the close ran on the driver's own mints
    assert "| rows | 3 |" in (tmp_path / "ledger.md").read_text("utf-8")

    assert json.loads((tmp_path / "close.json").read_text("utf-8"))[
        "n_certificates"] == 2
    assert "3 row(s) read, 0 superseded, 2 mint(s)" in captured.out


def test_the_ledger_exists_before_the_pass_does_any_work(monkeypatch,
                                                         tmp_path):
    """The 2026-09-10 kill left nothing because the out dir was made
    after `fp.run` returned.  Now the first key sees a header."""
    seen: list[str] = []
    _stubbed_pass(
        monkeypatch, tmp_path, certify=set(), keys=[(0, 0, 0, "C")],
        on_key=lambda _key: seen.append(
            (tmp_path / "ledger.jsonl").read_text("utf-8")))

    assert len(seen) == 1
    header = json.loads(seen[0].splitlines()[0])
    assert header["type"] == "header" and header["partial"] is True
    assert header["n_targets"] == 1 and header["rungs"] == ["L0"]


def test_a_read_pass_does_not_overwrite_the_ladders_mints(monkeypatch,
                                                          tmp_path):
    """Both commands can share one `--out`: the mint file is named after
    its ledger so the two cannot collide."""
    from analyzer import ledger as ledger_mod

    keys = [(0, 0, 0, "C"), (0, 0, 1, "C")]
    assert _stubbed_pass(monkeypatch, tmp_path, certify={keys[0]},
                         keys=keys) == 0
    ladder_mints = (tmp_path / "mints.jsonl").read_text("utf-8")

    monkeypatch.setattr(cli, "_load", lambda _args: _stub_run())
    assert cli.main(["read", "--run-dir", "x", "--out", str(tmp_path),
                     "--no-maps", "--workers", "1",
                     "--checkpoint-minutes", "0"]) == 0
    assert (tmp_path / "ledger-read.jsonl").exists()
    assert (tmp_path / "mints-read.jsonl").exists()
    assert (tmp_path / "mints.jsonl").read_text("utf-8") == ladder_mints
    assert len(list(ledger_mod.iter_rows(tmp_path / "ledger.jsonl"))) == 2
