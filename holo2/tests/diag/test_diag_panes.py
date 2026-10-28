"""The pane server's corpus-FREE claims: model, paint, refusal, layout.

DESIGN §10.3 / L12. Everything here is a function of values a test can
BUILD — a synthetic ``PaneModel``, an exploding source, a status
dictionary, a state-directory path — so it needs no session, no capture
and no decode.

THE SESSION-DRIVEN HALF MOVED AT H4 W1b (H4-PLAN R11). It drove the toy
providers over the H3 bench's synthetic corpus, and both retired with the
toys. A pane source needs genuine regions, a genuine window lattice, real
poses and a real done projection, which means a page the REAL generator
emitted — and the firewall keeps generators out of this tree. Those tests
(``test_diag_pane_source_e2e.py``) were deleted with the measure cleanup;
history has the driver. What stayed here is what never needed a decode.
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

from holo2.core.commit import CommitResult
from holo2.diag import panes, status as diag
from holo2.diag.panes import paint
from holo2.diag.panes import render as panes_render
from holo2.engine.snapshot import QueueView, RunSnapshot
from holo2.solve import TileState, tile_key

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class _Exploding:
    """A pane source whose every method fails (the inertness fixture)."""

    revision = 0

    def catalog(self) -> dict:
        raise RuntimeError("catalog exploded")

    def build(self, *args: object, **kwargs: object):
        raise RuntimeError("build exploded")


def _fetch(port: int, path: str) -> tuple[int, str, bytes]:
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return (response.status,
                    response.headers.get("Content-Type", ""),
                    response.read())
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type", ""), error.read()


# ---------------------------------------------------------- the blank frame

def test_an_unbound_observer_renders_a_frame_that_says_so() -> None:
    model = panes.PaneModel(revision=0, page=0, pages=(0,), row_id="none",
                            codec_id="none", capture=None, captures=(),
                            plane=None)
    png = panes.render_frame(model)
    assert png.startswith(PNG_MAGIC)
    with Image.open(io.BytesIO(png)) as image:
        assert image.size == panes.frame_size(model)


def test_the_rows_refuse_to_print_zero_for_an_unavailable_fact() -> None:
    rows = diag.status_rows({"commit_stream": {"commits": 0}})
    assert len(rows) == 6
    assert "unavailable" in rows[0]            # no session bound
    assert "unavailable" in rows[2]            # no orchestrator snapshot
    assert "unavailable" in rows[4]            # no tile map read


def test_an_exploding_pane_source_leaves_the_status_channel_up() -> None:
    provider = diag.StatusProvider()
    provider.publish(RunSnapshot(queue=QueueView(depth=1)))
    provider._frames = diag.FrameCache(_Exploding())
    status = provider.status()
    assert status["session"]["ready"] == {"depth": 1, "by_family": {}}
    assert status["panes_error"].startswith("RuntimeError")
    assert len(status["rows"]) == 6


def test_an_unbound_provider_serves_status_but_no_frame() -> None:
    provider = diag.StatusProvider()
    server = diag.serve(0, provider)
    assert server is not None
    try:
        code, _kind, body = _fetch(server.port, "/status")
        assert code == 200 and b'"panes"' not in body
        assert _fetch(server.port, "/frame/0.png")[0] == 404
    finally:
        server.stop()


# ------------------------------------------------------------------- paint

def test_the_page_pane_paints_every_tile_state_distinctly() -> None:
    """Each §5.2 state is a distinct visible chip, and the v1 sibling rule
    holds: an unseen SEGMENT of a touched tile is neutral (so partial
    stream success never reads as a whole-tile state), while an untouched
    tile keeps the ruled grid's own unseen fill."""
    states = np.zeros((2, 4, 4), np.uint8)
    evidence = np.zeros((4, 4), np.int32)
    for rank in (TileState.ADDRESSED, TileState.ATTEMPTED,
                 TileState.CERTIFIED):
        states[0, rank.value - 1, :] = rank.value    # stream C carries it
        evidence[rank.value - 1, :] = 3              # stream M stays UNKNOWN
    # Tile row 3 is touched by nothing at all and must stay grid-unseen.
    synthetic = panes.TilePlane(
        page=0, tiles_yx=(4, 4), stream_ids=("C", "M"), states=states,
        evidence=evidence)
    model = panes.PaneModel(
        revision=0, page=0, pages=(0,), row_id="synthetic",
        codec_id="synthetic", capture=None, captures=(), plane=synthetic)
    width, height = panes.pane_size((4, 4))
    raster = panes.page_pane(model, width, height)
    present = {tuple(colour) for colour in raster.reshape(-1, 3).tolist()}
    for rank in (TileState.ADDRESSED, TileState.ATTEMPTED,
                 TileState.CERTIFIED):
        assert tuple(panes_render.TILE_CHIPS[rank.value][0]) in present, (
            f"tile state {rank.name} is invisible in pane B")
    assert tuple(paint.CHIP_NEUTRAL[0]) in present     # unseen sibling
    assert tuple(paint.CHIP_UNSEEN[0]) in present      # untouched tile row
    fills = {tuple(chip[0]) for chip in panes_render.TILE_CHIPS.values()}
    assert len(fills) == 4, "the four states must not share a fill"


# -------------------------------------------------------- observer-only

def test_a_write_through_a_pane_path_is_unrepresentable() -> None:
    """The pane modules never construct a Write — checked as source text.

    ``publish.py`` writes FILES, which is the point of it; what no pane
    module may reach for is a *store* writer.
    """
    root = Path(panes.__file__).resolve().parent
    offenders = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in ("CommitBatch", "apply(", "put_array", "put_blob",
                       "snapshot()", "Write("):
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, (
        "a pane module reached for a writer: " + ", ".join(offenders))


# ------------------------------------------------- the terminal publish

def test_the_diag_directory_is_a_sibling_never_a_child(tmp_path: Path) -> None:
    """The store opens strictly; it must never be shown observer scribbles."""
    state = tmp_path / "run" / "state"
    directory = panes.diag_directory(state)
    assert directory == tmp_path / "run" / "state.diag"
    assert directory.parent == state.parent
    assert state not in directory.parents


def test_finalize_without_a_session_still_writes_what_it_has(
        tmp_path: Path) -> None:
    provider = diag.StatusProvider()
    provider.note_commit(CommitResult(
        commit_seq=1, batch_id="b1",
        changed_keys=(tile_key(0, 0, 0, "main"),), wakes=()))
    final = diag.finalize(provider, tmp_path / "state")
    assert final.ok, final.failures
    assert sorted(path.name for path in final.directory.iterdir()) == [
        "report.json", "status.json"]
    report = json.loads((final.directory / "report.json").read_text())
    assert report["outcome"]["status"] == "unavailable"
    assert report["commit_stream"]["commits"] == 1
