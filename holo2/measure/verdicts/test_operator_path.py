"""VERDICT 9: the OPERATOR PATH — one typed string, and the bytes come back.

    env/bin/python -m pytest holo2/measure/verdicts/test_operator_path.py -q

Everything else in this directory drives ``cli.decode`` with a row
already built. This one drives ``cli.main`` with an ARGV, from the page's
format id alone: no ``FormatRowSpec``, no geometry, no printer, no paper
— the identity string an operator types, and nothing besides the
capture's true DPI and where to put the answer.

WHY IT EXISTS (C5, 2026-08-22, RULINGS G6). ``--format`` replaced
``--coding`` + ``--tiles-y`` + ``--tiles-x``, and the argument surface is
pinned in ``holo2/tests/test_cli_surface.py`` against a STUBBED decode —
necessarily, since that tree may not import the generator (firewall).
So nothing anywhere proved that the string reaches a payload: that a
format id resolves to the row, the row composes the real families, the
families decode the real pixels, and ``main`` publishes the recovered
object and exits 0. CRITIQUE-verify §4.4 noted `src/holo` lacks this bar
too (its ``--format`` e2e coverage is ``generate``/``capacity``, and its
one decode CLI test deliberately fails downstream of the flags).

The fork it prevents is a whole class rather than one bug: a CLI that
parses beautifully and cannot decode. Every seam between the flag and
the bytes is on this path exactly once — resolve, row, providers,
source, close, publish — and a break in any of them is invisible to a
stubbed decode and to a library-level e2e alike.

THE SMALLEST FIXTURE, deliberately: the architecture spine's own page
(``_fixtures.SPINE_FORMAT``, ``c3-k-r0550@8x8``), rendered CLEAN. 64
tiles clears the L9 metadata floor of 48 with 16 to spare, c3 keeps the
raster small at 3 dots a cell, and a channel is not the subject here —
run channel already decodes this shape through the measured e032 warp
with a 2% cell error rate, and duplicating that would buy a slower copy
of an existing verdict. What this file adds is the SKIN.
"""
from __future__ import annotations

from pathlib import Path

from _fixtures import SPINE_FORMAT, build_page, render
from conftest import CLEAN_DITHER, PX_PER_DOT

from holo2 import cli


def test_a_format_id_typed_at_the_cli_returns_the_volume(
        tmp_path: Path) -> None:
    """One argv, exit 0, and the recovered object is the emitted payload."""
    page = build_page(SPINE_FORMAT)
    capture = render(page.dots, tmp_path / "sheet.png",
                     px_per_dot=PX_PER_DOT, cell_dots=page.cell_dots,
                     noise_sigma=CLEAN_DITHER)
    output = tmp_path / "recovered.bin"
    code = cli.main([
        "--scan", str(capture.path), "--dpi", str(capture.dpi),
        "--state-dir", str(tmp_path / "state"), "--output", str(output),
        # An EPHEMERAL diag port: the endpoint is always on (user ruling
        # 2026-08-09) and a verdict may not depend on 8024 being free.
        "--diag-port", "0",
        "--format", SPINE_FORMAT])
    assert code == cli.EXIT_VERIFIED, "the operator path did not close"
    assert output.read_bytes() == page.payload

    # AND THE STATE IT LEFT RESUMES WITH NO IDENTITY ARGUMENT — the other
    # half of the ruling, on a state a real decode wrote rather than one
    # a test composed. It is terminal and VERIFIED, so this run does no
    # work: what is proven is that the persisted ``format_row_id``
    # reconstructs its row (the total resolver, FORMAT-SPACE §10) and
    # that the second recovery is the same volume. The output object is a
    # new name because holo2 never overwrites a recovered payload.
    again = tmp_path / "recovered-again.bin"
    resumed = cli.main([
        "--state-dir", str(tmp_path / "state"), "--output", str(again),
        "--diag-port", "0"])
    assert resumed == cli.EXIT_VERIFIED
    assert again.read_bytes() == page.payload
