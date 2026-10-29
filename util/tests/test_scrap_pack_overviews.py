"""Focused tests for the disposable corpus-overview companion utility."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]  # 2026-09-06: moved to util/tests/
sys.path.insert(0, str(ROOT))

from util.scrap_pack_overviews import (discover_images, infer_cell_px,
                                       process_one)


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.full((8, 9), 240, np.uint8)).save(path)


def test_pitch_inference_is_explicit_and_token_bounded(tmp_path: Path) -> None:
    assert infer_cell_px(
        tmp_path / "unused.png", Path("scan-8ppc.png")
    )[:2] == (8.0, "path ppc")
    assert infer_cell_px(
        tmp_path / "unused.tiff", Path("capture-c2-canon-4800.tiff")
    )[:2] == (16.0, "c2 + path DPI")
    assert infer_cell_px(
        tmp_path / "unused.png", Path("capture-c3-hp-1200.png")
    )[:2] == (6.0, "c3 + path DPI")
    assert infer_cell_px(
        tmp_path / "unused.png", Path("incidentalabc2-4800.png")
    )[:2] == (24.0, "fallback default")
    assert infer_cell_px(
        tmp_path / "unused.png", Path("compare-c2-c3-4800.png")
    )[:2] == (24.0, "fallback default")


def test_discovery_excludes_output_and_optionally_admin_trees(
        tmp_path: Path) -> None:
    output = tmp_path / "build" / "overviews"
    normal = tmp_path / "scans" / "input.png"
    admin = tmp_path / "env" / "asset.png"
    worktree = tmp_path / ".claude" / "worktrees" / "copy.png"
    git_file = tmp_path / ".git" / "hidden.png"
    recursive = output / "old.overview.png"
    for path in (normal, admin, worktree, git_file, recursive):
        _png(path)

    assert discover_images(tmp_path, output) == [normal.resolve()]
    assert discover_images(tmp_path, output, include_admin=True) == sorted(
        [worktree.resolve(), admin.resolve(), normal.resolve()],
        key=lambda path: path.relative_to(tmp_path).as_posix(),
    )


def test_cmyk_input_gets_explicit_unsupported_overview(tmp_path: Path) -> None:
    tifffile = pytest.importorskip("tifffile")
    source = tmp_path / "scan-cmyk.tiff"
    tifffile.imwrite(
        source, np.zeros((20, 30, 4), np.uint8), photometric="separated"
    )
    output = tmp_path / "overviews"

    record = process_one(tmp_path, output, source)

    assert record["status"] == "unsupported"
    assert "CMYK" in record["error"]
    overview = output / record["overview"]
    assert overview.is_file()
    with Image.open(overview) as image:
        assert image.format == "PNG"


def test_ycbcr_input_gets_explicit_unsupported_overview(tmp_path: Path) -> None:
    tifffile = pytest.importorskip("tifffile")
    source = tmp_path / "scan-ycbcr.tiff"
    tifffile.imwrite(
        source, np.zeros((20, 30, 3), np.uint8), photometric="ycbcr"
    )

    record = process_one(tmp_path, tmp_path / "overviews", source)

    assert record["status"] == "unsupported"
    assert "YCBCR" in record["error"]
