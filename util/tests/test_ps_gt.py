"""util/ps_gt.py re-derives the emitted GT from the PostScript alone, bit for bit."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from holo.format.resolve import resolve_format_ref
from holo.gen.emit import emit_volume
from holo.gen.plan import max_payload_bytes
from util.ps_gt import count_paint_operators, holo_gt, main, parse_bitmaps


@pytest.fixture(scope="module", params=["c3-k-r0550@10x10", "c2-cmy8-r0550@10x10"])
def volume(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    spec = resolve_format_ref(request.param)
    n_bytes = max_payload_bytes(spec, 0.5, 1)
    out = tmp_path_factory.mktemp("ps_gt") / "volume"
    emit_volume(spec, bytes(i & 0xFF for i in range(n_bytes)), 0.5, out, paper="A4-6mm")
    return out, json.loads((out / "manifest.json").read_text())


def test_one_bitmap_placed_at_the_emitted_origin(volume: tuple[Path, dict]) -> None:
    out, manifest = volume
    text = (out / "page000.ps").read_bytes()
    bms = parse_bitmaps(text)
    assert len(bms) == count_paint_operators(text) == 1
    bm = bms[0]
    assert (bm.y_dots, bm.x_dots) == tuple(manifest["origin_dots_yx"])
    assert bm.dpi_xy == (600, 600) and bm.page == 1
    assert bm.kind == ("cmyk" if "cmy8" in manifest["spec_id"] else "mask")


def test_gt_is_bit_identical_to_the_emitted_npy(volume: tuple[Path, dict]) -> None:
    out, manifest = volume
    gt = holo_gt(parse_bitmaps((out / "page000.ps").read_bytes())[0])
    emitted = np.load(out / "page000_gt.npy", allow_pickle=False)
    assert gt.dtype == emitted.dtype and gt.shape == emitted.shape
    assert np.array_equal(gt, emitted)
    assert hashlib.sha256(gt.tobytes()).hexdigest() == manifest["pages"][0]["gt_sha256"]


def test_cli_writes_only_against_the_manifest_sha(volume: tuple[Path, dict], tmp_path: Path) -> None:
    out, manifest = volume
    target = tmp_path / "gt.npy"
    assert main([str(out / "page000.ps"), "--out", str(target), "--expect-sha256", "0" * 64]) == 1
    assert not target.exists()
    assert main([str(out / "page000.ps"), "--out", str(target),
                 "--expect-sha256", manifest["pages"][0]["gt_sha256"]]) == 0
    assert (target.read_bytes() == (out / "page000_gt.npy").read_bytes())
