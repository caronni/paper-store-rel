"""analyzer.mirror — a run dir's rasters, rebuilt locally (PLAN §6).

Everything here is synthetic: a 200x160 RGB TIFF and a fabricated
`argv`/`report.json`/`events.jsonl`/`facts.npz` around it, so the whole
module runs in a second and needs no capture on a mount.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from analyzer import mirror

FORMAT_REF = "L:c2-cmy8-r0547@53x37"
DPI = 2400.0
SHAPE_YX = (200, 160)
LEVELS_PPC = ("2", "4", "8")


def _write_tiff(path: Path) -> str:
    import tifffile

    rng = np.random.default_rng(20260903)
    pixels = rng.integers(0, 256, (*SHAPE_YX, 3), dtype=np.uint8)
    tifffile.imwrite(path, pixels)
    return mirror.intake.sha256_file(path)


def _source_run(tmp_path: Path, *, capture_id: str | None = None,
                argv: str | None = None) -> tuple[Path, Path, str]:
    """A source run dir + the TIFF it names.  Returns (src, tiff, sha)."""
    tiff = tmp_path / "tiny-capture.tiff"
    sha = _write_tiff(tiff)
    declared = capture_id or sha
    src = tmp_path / "src-run"
    src.mkdir()
    (src / "argv").write_text(
        argv if argv is not None else
        f"/repo/holo3/__main__.py decode {tiff} --dpi {DPI:g} "
        f"--format {FORMAT_REF} --out /repo/x.bin --run-dir /repo/x "
        f"--workers 6 --pages 100 --complete\n", "utf-8")
    (src / "report.json").write_text(json.dumps({
        "capture_facts": [{
            "capture": declared, "ordinal": 0, "dpi": DPI, "channels": 3,
            "levels_ppc": list(LEVELS_PPC), "shape_yx": list(SHAPE_YX)}],
        "captures": [{"ordinal": 0, "sha12": declared[:12]}],
        "pages": [0], "close": {}}), "utf-8")
    (src / "events.jsonl").write_text(json.dumps({
        "type": "RunOpen", "format_id": FORMAT_REF, "pitch_in": 1 / 300,
        "tiles_yx": [53, 37]}) + "\n", "utf-8")
    (src / "facts.npz").write_bytes(b"not read by the mirror")
    return src, tiff, sha


# ------------------------------------------------------------ argv parsing

def test_parse_decode_argv_pairs_scans_with_dpi():
    scans, dpis = mirror.parse_decode_argv(
        "/repo/holo3/__main__.py decode a.tiff b.tiff --dpi 2400 "
        "--dpi 4800 --format L:x@1x1 --out o --run-dir r --diag 8023")
    assert scans == ("a.tiff", "b.tiff")
    assert dpis == (2400.0, 4800.0)


def test_parse_decode_argv_reads_options_the_parser_has_dropped():
    """Sheet J's argv carries `--pages 100`, which holo3 no longer takes."""
    scans, dpis = mirror.parse_decode_argv(
        "/repo/holo3/__main__.py decode s.tiff --dpi 2400 --pages 100 "
        "--format=L:x@1x1 --out o")
    assert (scans, dpis) == (("s.tiff",), (2400.0,))


def test_parse_decode_argv_refuses_mismatched_dpi_count():
    with pytest.raises(mirror.MirrorError, match="exactly one"):
        mirror.parse_decode_argv("x decode a.tiff b.tiff --dpi 2400 --out o")


def test_parse_decode_argv_refuses_an_unrecognised_positional():
    with pytest.raises(mirror.MirrorError, match="will not guess"):
        mirror.parse_decode_argv("x decode a.raw --dpi 2400 --out o")


def test_resolve_capture_path_uses_the_basename_under_tiff_dir(
        tmp_path: Path):
    (tmp_path / "moved.tiff").write_bytes(b"x")
    found = mirror.resolve_capture_path(
        "/elsewhere/on/a/mount/moved.tiff", tiff_dir=tmp_path)
    assert found == tmp_path / "moved.tiff"
    with pytest.raises(mirror.MirrorError, match="not found"):
        mirror.resolve_capture_path("absent.tiff", tiff_dir=tmp_path)


# ---------------------------------------------------------------- the build

def test_mirror_builds_the_capture_directory(tmp_path: Path):
    src, _tiff, sha = _source_run(tmp_path)
    out = tmp_path / "out-run"
    result = mirror.mirror(src, out, log=lambda _line: None)

    assert sorted(result["copied"]) == sorted(mirror.MIRROR_FILES)
    assert result["format_ref"] == FORMAT_REF
    plane_dir = out / sha[:12]
    assert plane_dir.is_dir(), "the directory is named by sha256[:12]"
    for index, ppc in enumerate(LEVELS_PPC):
        for plane in ("r", "g", "b"):
            path = mirror.intake.plane_path(plane_dir, index, plane)
            assert path.exists(), f"{path.name} (ppc {ppc}) is missing"
    native = np.load(mirror.intake.plane_path(plane_dir, 2, "r"),
                     mmap_mode="r")
    assert native.shape == SHAPE_YX
    assert np.load(mirror.intake.plane_path(plane_dir, 0, "r"),
                   mmap_mode="r").shape == (50, 40)
    row, = result["captures"]
    assert row["ingested"] is True and row["sha12"] == sha[:12]
    assert row["levels"] == list(LEVELS_PPC) and row["dpi"] == DPI
    assert result["verified"][0]["sha12"] == sha[:12]


def test_mirror_is_idempotent(tmp_path: Path):
    src, _tiff, sha = _source_run(tmp_path)
    out = tmp_path / "out-run"
    mirror.mirror(src, out, log=lambda _line: None)
    stamps = {path.name: path.stat().st_mtime_ns
              for path in sorted((out / sha[:12]).iterdir())}

    again = mirror.mirror(src, out, log=lambda _line: None)
    assert again["copied"] == [], "the four small files were already there"
    row, = again["captures"]
    assert row["ingested"] is False and row["seconds"] == 0.0
    assert {path.name: path.stat().st_mtime_ns
            for path in sorted((out / sha[:12]).iterdir())} == stamps


def test_mirror_rebuilds_a_truncated_capture(tmp_path: Path):
    src, _tiff, sha = _source_run(tmp_path)
    out = tmp_path / "out-run"
    mirror.mirror(src, out, log=lambda _line: None)
    mirror.intake.plane_path(out / sha[:12], 1, "g").unlink()

    row, = mirror.mirror(src, out, log=lambda _line: None)["captures"]
    assert row["ingested"] is True
    assert mirror.intake.plane_path(out / sha[:12], 1, "g").exists()


def test_mirror_refuses_a_capture_that_hashes_differently(tmp_path: Path):
    wrong = "0" * 64
    src, _tiff, sha = _source_run(tmp_path, capture_id=wrong)
    with pytest.raises(mirror.MirrorError) as excinfo:
        mirror.mirror(src, tmp_path / "out-run", log=lambda _line: None)
    assert sha[:12] in str(excinfo.value) and wrong[:12] in str(excinfo.value)


def test_mirror_refuses_a_dpi_that_argv_and_report_disagree_on(
        tmp_path: Path):
    src, tiff, _sha = _source_run(tmp_path)
    (src / "argv").write_text(
        f"x decode {tiff} --dpi 1200 --format {FORMAT_REF} --out o", "utf-8")
    with pytest.raises(mirror.MirrorError, match="--dpi"):
        mirror.mirror(src, tmp_path / "out-run", log=lambda _line: None)


def test_mirror_refuses_to_write_into_its_own_source(tmp_path: Path):
    src, _tiff, _sha = _source_run(tmp_path)
    with pytest.raises(mirror.MirrorError, match="same directory"):
        mirror.mirror(src, src, log=lambda _line: None)


def test_mirror_honours_a_format_ref_override(tmp_path: Path):
    """The override drives the level ladder: pitch and family come from it."""
    src, _tiff, sha = _source_run(tmp_path)
    (src / "events.jsonl").write_text(json.dumps({
        "type": "RunOpen", "format_id": "c2-cmy8-r0547@53x37"}) + "\n",
        "utf-8")
    result = mirror.mirror(src, tmp_path / "out-run", format_ref=FORMAT_REF,
                           log=lambda _line: None)
    assert result["format_ref_declared"] == "c2-cmy8-r0547@53x37"
    assert result["format_ref"] == FORMAT_REF
    assert result["captures"][0]["sha12"] == sha[:12]


def test_mirror_uses_tiff_dir_for_an_unreachable_argv_path(tmp_path: Path):
    src, tiff, sha = _source_run(tmp_path)
    moved = tmp_path / "tiffs"
    moved.mkdir()
    tiff.rename(moved / tiff.name)
    with pytest.raises(mirror.MirrorError, match="not found"):
        mirror.mirror(src, tmp_path / "a", log=lambda _line: None)
    result = mirror.mirror(src, tmp_path / "b", tiff_dir=moved,
                           log=lambda _line: None)
    assert result["captures"][0]["sha12"] == sha[:12]


def test_verify_run_dir_names_an_absent_directory(tmp_path: Path):
    src, _tiff, sha = _source_run(tmp_path)
    report = json.loads((src / "report.json").read_text("utf-8"))
    with pytest.raises(mirror.MirrorError) as excinfo:
        mirror.verify_run_dir(tmp_path / "empty", report, Fraction(1, 300),
                              mirror.identity.Family.CMY8)
    assert sha[:12] in str(excinfo.value)


def test_capture_complete_is_false_on_a_wrong_shape(tmp_path: Path):
    levels = mirror.intake.build_levels(DPI, Fraction(1, 300), SHAPE_YX)
    plane_dir = tmp_path / "cap"
    plane_dir.mkdir()
    for level in levels:
        for plane in ("r", "g", "b"):
            np.save(mirror.intake.plane_path(plane_dir, level.index, plane),
                    np.zeros(level.shape_px, np.uint8))
    assert mirror.capture_complete(plane_dir, 3,
                                   mirror.identity.Family.CMY8, levels)
    np.save(mirror.intake.plane_path(plane_dir, 0, "b"),
            np.zeros((3, 3), np.uint8))
    assert not mirror.capture_complete(plane_dir, 3,
                                       mirror.identity.Family.CMY8, levels)


def test_mirror_refuses_an_out_dir_holding_another_run(tmp_path: Path):
    """`--out` reused across runs would blend two of them (reviewer fix)."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first, _tiff_a, _sha_a = _source_run(tmp_path / "a")
    second, _tiff_b, _sha_b = _source_run(tmp_path / "b", capture_id="1" * 64)
    out = tmp_path / "out-run"
    mirror.copy_run_files(first, out)
    with pytest.raises(mirror.MirrorError, match="another run's directory"):
        mirror.mirror(second, out, log=lambda _line: None)


def test_copy_run_files_keeps_a_standing_copy_when_the_source_is_gone(
        tmp_path: Path):
    """The offline-resume promise: `out` wins, and nothing is compared."""
    src, _tiff, _sha = _source_run(tmp_path)
    out = tmp_path / "out-run"
    assert sorted(mirror.copy_run_files(src, out)) == sorted(
        mirror.MIRROR_FILES)
    for name in mirror.MIRROR_FILES:
        (src / name).unlink()
    assert mirror.copy_run_files(src, out) == ()
