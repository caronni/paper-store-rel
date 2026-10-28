"""Review pins for the GAPS-2026-09-03 work (reviewer, 2026-09-03).

The defect these exist for: `arms._page_ctx_labels` called
`frame.known_frame` without its REQUIRED keyword-only `metadata_known`, so
every `page` and `local5` context fit raised `TypeError` on its first
sampled tile.  Nothing caught it, because the module's own tests drive
`calibrate._apply_local_context` with a hand-built context object and
`local_context=None` — both of which bypass the fit entirely.

So the pins here are on the SEAM, not on the arithmetic: the call has to
bind against the real signature, and the fit has to stay blind.  They cost
no snapshot and no raster.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest

from analyzer import arms
from analyzer import frame as frame_mod

MODULE = Path(arms.__file__)


def _call_kwargs(func, callee: str) -> set[str]:
    """The keyword names `func`'s source passes to `callee(...)`."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = (target.attr if isinstance(target, ast.Attribute)
                else getattr(target, "id", None))
        if name != callee:
            continue
        out |= {kw.arg for kw in node.keywords if kw.arg is not None}
    return out


def test_the_page_context_fit_binds_against_known_frames_real_signature():
    """The pin for the defect: required kwargs are actually passed.

    `known_frame` grew `metadata_known` as keyword-only WITHOUT a default,
    which is the right shape — a frame either was or was not told the
    metadata bit and nobody should get to be vague about it.  That makes
    every caller responsible for saying so, and a caller that forgets does
    not fail at import or at review, it fails on the first real tile.
    """
    required = {
        name for name, parameter in
        inspect.signature(frame_mod.known_frame).parameters.items()
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty}
    assert "metadata_known" in required, (
        "the signature moved; this pin is about REQUIRED keyword-only "
        "arguments of known_frame and needs to be re-read, not deleted")
    passed = _call_kwargs(arms._page_ctx_labels, "known_frame")
    assert required <= passed, (
        f"_page_ctx_labels omits {sorted(required - passed)} — the page "
        f"and local5 context fits raise TypeError on their first tile")


@pytest.mark.parametrize("func", [arms.page_context, arms.local_context,
                                  arms._page_ctx_labels])
def test_the_context_fits_take_no_truth(func):
    """Blindness, at the only scope that matters here: the arguments.

    These three read rasters and certificates and nothing else.  A `truth`
    or `oracle` argument appearing on one of them would mean the
    correction applied to a target was fitted with the answer in hand, so
    the parameter list is the pin — cheaper than a taint trace and it
    fails at the moment somebody adds the parameter.
    """
    names = set(inspect.signature(func).parameters)
    assert not (names & {"truth", "oracle", "census", "answer"}), (
        f"{func.__name__} takes {sorted(names)}")
    source = inspect.getsource(func)
    for forbidden in ("truth.", "oracle.", "import truth", "import oracle"):
        assert forbidden not in source, f"{func.__name__} mentions {forbidden}"


def test_the_neighbourhood_never_contains_its_own_target():
    """No certificate of the tile being read enters the correction.

    The whole blindness argument for `local5` is that the 5x5 block
    excludes its centre, so this is pinned on the geometry directly —
    including at the page's corners and edges, where the clip is what
    decides how many neighbours there are.
    """
    class _Inputs:
        tiles_yx = (7, 9)

    inputs = _Inputs()
    for ty in range(7):
        for tx in range(9):
            tiles = arms.neighbourhood_tiles(inputs, ty, tx, 2)
            assert (ty, tx) not in tiles
            assert len(set(tiles)) == len(tiles)
            assert all(0 <= y < 7 and 0 <= x < 9 for y, x in tiles)
    assert len(arms.neighbourhood_tiles(inputs, 3, 4, 2)) == 24
    assert len(arms.neighbourhood_tiles(inputs, 0, 0, 2)) == 8


def test_the_memo_keys_carry_the_certificate_token():
    """Withholding must not come back out of the cache.

    `frame._certs_token` is what makes a `--withhold` mapping a different
    cache line from the full one; a memo key that left it out would hand a
    withheld run the full run's fit, and the positive control would be
    measuring nothing.  Pinned on the source because building two real
    certificate mappings costs a 6.5 GB snapshot.
    """
    for func in (arms.page_context, arms.local_context):
        source = inspect.getsource(func)
        assert "_certs_token" in source, f"{func.__name__}"
        # the whole tuple, not the first line of it
        assignment = source.split("cache_key = ")[1].split("hit = ")[0]
        assert "token" in assignment, (
            f"{func.__name__}: the certs token is computed but not in the "
            f"memo key")
