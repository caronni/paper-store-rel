"""The operator's manual must be runnable (W8 B5).

README.md spells commands in two kinds of fenced block: the ordinary
prose ones, which carry ellipses and shell variables on purpose, and the
ones tagged ```analyzer-cmd, which are the isolation and composition
commands of `APPROACHES-2026-09-06.md` §1/§3 spelled IN FULL.  Only the
tagged ones are harvested here, and every one of them must parse through
the real parser, name a real profile, real arms, real rules, real rungs
and knobs the CLI accepts.  A doc line that has rotted away from the code
is then a test failure, not a surprise at hour three of a pass.
"""
from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from analyzer import cli
from analyzer.arms import parse_arm
from analyzer.combine import RULES
from analyzer.fixedpoint import expand_rungs
from analyzer.types import KNOWN_RUNGS, PROFILES

README = Path(cli.__file__).with_name("README.md")
DESIGN = Path(cli.__file__).with_name("DESIGN.md")
APPROACHES = Path(cli.__file__).with_name("APPROACHES-2026-09-06.md")

#: The fence the harvester looks for.
TAG = "analyzer-cmd"


def analyzer_cmd_blocks(text: str) -> list[str]:
    """Every ```analyzer-cmd block's body, in document order."""
    blocks: list[str] = []
    collecting: list[str] | None = None
    for line in text.splitlines():
        if collecting is None:
            if line.strip() == f"```{TAG}":
                collecting = []
            continue
        if line.strip() == "```":
            blocks.append("\n".join(collecting))
            collecting = None
        else:
            collecting.append(line)
    assert collecting is None, "an unterminated ```analyzer-cmd fence"
    return blocks


def argv_of(block: str) -> list[str]:
    """The block as one argv, with the `python -m analyzer` prefix cut."""
    argv = shlex.split(block.replace("\\\n", " "))
    assert "-m" in argv and "analyzer" in argv, block
    return argv[argv.index("analyzer", argv.index("-m")) + 1:]


def test_the_readme_carries_analyzer_cmd_blocks():
    """A harvester that finds nothing would pass every test below."""
    blocks = analyzer_cmd_blocks(README.read_text("utf-8"))
    assert len(blocks) >= 8, f"only {len(blocks)} analyzer-cmd blocks"


@pytest.mark.parametrize(
    "block", analyzer_cmd_blocks(README.read_text("utf-8")))
def test_readme_analyzer_cmd_blocks_parse(block):
    assert "$" not in block, "no shell variables in an analyzer-cmd block"
    for ellipsis in ("…", "..."):
        assert ellipsis not in block, "no ellipsis in an analyzer-cmd block"
    argv = argv_of(block)
    args = cli.build_parser().parse_args(argv)
    assert args.command == argv[0]
    profile = getattr(args, "profile", None)
    if profile:
        assert profile in PROFILES, f"unknown profile {profile!r}"
    for arm in cli._list(getattr(args, "arms", None), ()):
        parse_arm(arm)
    for rule in cli._list(getattr(args, "rules", None), ()):
        assert rule in RULES, f"unknown rule {rule!r}"
    for rung in expand_rungs(cli._list(getattr(args, "rungs", None), ())):
        assert rung in KNOWN_RUNGS, f"unknown rung {rung!r}"
    for item in getattr(args, "knob", None) or ():
        cli.parse_knob(item)


def test_the_analyzer_cmd_commands_reach_a_config():
    """Not only the parser: the knob bag and the profile land, too.

    `_config` is what refuses a malformed patch/pure knob and applies the
    precedence rule, so a documented command that cannot be configured
    would exit 2 for the operator on line one.
    """
    for block in analyzer_cmd_blocks(README.read_text("utf-8")):
        args = cli.build_parser().parse_args(argv_of(block))
        if args.command in ("ladder", "read", "controls", "score"):
            config = cli._config(args)
            assert config.arms and config.rules


def test_every_profile_is_named_in_the_operator_manual():
    """A profile nobody documented is a profile nobody runs.

    This is the guard that would have caught the gap W8 B5 found: B8 added
    `patch-then-pure` and `everything+patch+pure` and documented them in
    the README and PLAN, but the design of record (DESIGN §6.2) and the
    approach enumeration (APPROACHES §2) still said "there is no
    reroll-only arm list".  The README is the operator's door and must
    name every profile the code offers.
    """
    text = README.read_text("utf-8")
    missing = [name for name in PROFILES if f"`{name}`" not in text]
    assert not missing, f"profiles absent from README: {missing}"


def test_every_w8_profile_is_named_in_the_approach_enumeration():
    """APPROACHES §2 is the composition record: every profile this wave
    added is a composition and must be enumerated there."""
    text = APPROACHES.read_text("utf-8")
    w8 = [name for name in PROFILES
          if name.startswith(("patch", "pure")) or name.endswith("+pure")]
    assert len(w8) >= 8, sorted(w8)
    missing = [name for name in w8 if f"`{name}`" not in text]
    assert not missing, f"W8 profiles absent from APPROACHES: {missing}"


def test_the_design_names_every_unmix_mode_and_every_rung():
    """DESIGN is normative: an arm head or a rung the code dispatches but
    the design never mentions is an undocumented mechanism."""
    import re
    from analyzer.unmix import UNMIX_MODES
    text = DESIGN.read_text("utf-8")
    missing_modes = [mode for mode in UNMIX_MODES if f"`{mode}`" not in text]
    assert not missing_modes, f"unmix modes absent from DESIGN: {missing_modes}"
    # the §6 table spells a rung bare and backticks its alias
    # (`| L0 \`prod60\` |`), so this one is a word match, not a code span
    missing_rungs = [rung for rung in KNOWN_RUNGS
                     if not re.search(rf"\b{rung}\b", text)]
    assert not missing_rungs, f"rungs absent from DESIGN: {missing_rungs}"


def test_the_documents_agree_on_the_placement():
    """The reroll-only placement changed a sentence that three documents
    stated as a fact ("every arm in `arms` is a selection candidate").
    Whatever they say now, all three must name the mechanism."""
    for path in (README, DESIGN, APPROACHES):
        text = path.read_text("utf-8")
        assert "reroll_only_arms" in text, f"{path.name} misses the placement"


def test_the_auto_knobs_are_auto_in_every_profile_the_manual_claims_them_for():
    """The one exception is spelled out, in the code AND in the prose.

    README §2.4's table says the patch family's geometry knobs take
    `"auto"` and that `"auto"` is what the `patch` and `pure` profiles
    ask for.  `_PURE_KNOBS` names ONE of them — `patch_samples_per_cell`
    at 16 — because a coarser sampling is a different grid and would
    throw the 5x5 neighbourhood's harvested rows away.  Neither half may
    move without the other (review 2026-09-06: the code carried the
    exception and both documents claimed there was none).
    """
    from analyzer.types import _AUTO_PATCH_KNOBS, _PURE_KNOBS

    #: `patch-then-pure` / `everything+patch+pure` are PATCH profiles
    #: with the pure arms placed in the re-roll, so they carry the patch
    #: family's knobs (B8 says so in `types.py`: the two-pass form is
    #: "what an operator should reach for when the pure path wants knobs
    #: of its own").  Only the three `pure*` profiles carry `_PURE_KNOBS`.
    exceptions = {"pure", "pure-self", "pure-refit"}
    for name in ("patch", "patch-self", "patch-refit", "patch-affine",
                 "everything+patch", "patch-then-pure",
                 "everything+patch+pure"):
        knobs = PROFILES[name]["knobs"]
        for knob in _AUTO_PATCH_KNOBS:
            assert knobs.get(knob) == "auto", (name, knob)
    for name in sorted(exceptions):
        knobs = PROFILES[name]["knobs"]
        named = {knob for knob in _AUTO_PATCH_KNOBS
                 if knobs.get(knob) != "auto"}
        assert named == {"patch_samples_per_cell"}, (name, named)
        assert knobs["patch_samples_per_cell"] == 16
    assert _PURE_KNOBS["patch_samples_per_cell"] == 16
    readme = README.read_text("utf-8")
    assert "The one exception, and why." in readme
