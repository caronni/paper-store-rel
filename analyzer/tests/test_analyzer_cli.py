"""W2 — `analyzer.cli`: the operator's door (PLAN §5).

Parser shape first (a flag that silently does not exist is the classic
CLI bug), then one real `census` run against the sheet-I run dir, which
is also the smoke test PLAN §3 asks for.
"""

from __future__ import annotations

import json

import pytest

from analyzer import cli

from ._analyzer_fixtures import I_RUN_DIR, needs_i_run


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
            ("census", ["--run-dir", "/tmp/x"]),
            ("read", ["--run-dir", "/tmp/x"]),
            ("ladder", ["--run-dir", "/tmp/x"]),
            ("controls", ["--run-dir", "/tmp/x"]),
            ("close", ["--run-dir", "/tmp/x"]),
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
        args = parser.parse_args([command, "--run-dir", "/tmp/x"])
        name = flag.lstrip("-").replace("-", "_")
        assert hasattr(args, name), f"{command} has no {flag}"


@pytest.mark.parametrize("command", ["census", "read", "ladder", "controls",
                                     "close", "export-facts"])
def test_no_run_command_takes_a_payload(command):
    """RULED 2026-09-04: `--gt-dir` and `--payload` live on `score` only."""
    parser = cli.build_parser()
    argv = (["--snapshot", "/tmp/f.npz", "--ledger", "/tmp/l.jsonl",
             "--out", "/tmp/n.npz"] if command == "export-facts"
            else ["--run-dir", "/tmp/x"])
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


def test_open_after_is_a_target_spec():
    args = cli.build_parser().parse_args(
        ["ladder", "--run-dir", "/tmp/x", "--targets",
         "open-after /tmp/a.jsonl,/tmp/b.jsonl"])
    assert args.targets.startswith("open-after ")


def test_ladder_carries_the_pass_flags():
    args = cli.build_parser().parse_args(
        ["ladder", "--run-dir", "/tmp/x", "--targets", "band:dead",
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
    args = cli.build_parser().parse_args(["ladder", "--run-dir", "/tmp/x"])
    assert cli._config(args).max_generations == 1


def test_controls_carries_every_withhold_door():
    args = cli.build_parser().parse_args(
        ["controls", "--run-dir", "/tmp/x", "--parity", "50",
         "--withhold-run-mints"])
    assert args.parity == 50 and args.withhold_run_mints is True
    args = cli.build_parser().parse_args(
        ["controls", "--run-dir", "/tmp/x", "--withhold-source",
         "tiles/planek150,tiles/swim150"])
    assert cli._list(args.withhold_source, ()) == ("tiles/planek150",
                                                   "tiles/swim150")
    args = cli.build_parser().parse_args(
        ["controls", "--run-dir", "/tmp/x", "--holdout-stratified",
         "Y:tiles/planek150=60,C:tiles/local150=20"])
    assert args.holdout_stratified == (
        "Y:tiles/planek150=60,C:tiles/local150=20")


def test_halo_override_applies_to_every_stream():
    args = cli.build_parser().parse_args(
        ["ladder", "--run-dir", "/tmp/x", "--halo-cells", "24"])
    assert cli._config(args).halo_cells == {"C": 24, "M": 24, "Y": 24}


def test_list_falls_back_to_the_default():
    assert cli._list(None, ("a", "b")) == ("a", "b")
    assert cli._list("x, y ,", ("a",)) == ("x", "y")


# --------------------------------------------------------- the smoke run

@needs_i_run
def test_census_smoke_on_sheet_i(tmp_path, capsys):
    code = cli.main([
        "census", "--run-dir", str(I_RUN_DIR), "--out", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr().out
    print(captured)
    assert "residue 3" in captured
    assert (tmp_path / "census.jsonl").exists()
    ranks = json.loads((tmp_path / "census-rank.json").read_text("utf-8"))
    assert ranks["rank_report"] == ranks["rank_recomputed"] == 5277
    assert ranks["agree"] is True


@needs_i_run
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
