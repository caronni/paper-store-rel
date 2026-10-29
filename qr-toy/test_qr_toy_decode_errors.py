"""Acquisition failures stay local, and reports distinguish verification errors."""

import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from common import format_parts
from generate import generate
from decode import decode
import acquire


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("decode-errors") / "generated"
    generate(np.random.default_rng(971).bytes(263), output)
    return output


def test_triangle_is_rejected_without_losing_other_components() -> None:
    image = Image.new("L", (1000, 450), 255)
    ImageDraw.Draw(image).polygon([(80, 80), (340, 80), (80, 340)], fill=0)
    pixels = np.asarray(image, dtype=float).copy() / 255
    with pytest.raises(ValueError, match="no plausible complete tile"):
        acquire.segment(pixels, 3, lambda *_: None)

    # A separate square ink field remains a usable proposal despite the triangle.
    cells = np.random.default_rng(7).integers(0, 2, (64, 64))
    pixels[80:336, 650:906] = np.repeat(np.repeat(cells, 4, 0), 4, 1)
    _, quads = acquire.segment(pixels, 3, lambda *_: None)
    assert quads
    assert all(quad[:, 0].mean() > 600 for quad in quads)


def test_singular_proposal_does_not_abort_decode(
    tmp_path: Path, generated: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = acquire.segment

    def segment_with_bad_proposal(*args, **kwargs):
        normalized, quads = original(*args, **kwargs)
        return normalized, [np.zeros((4, 2)), *quads]

    monkeypatch.setattr(acquire, "segment", segment_with_bad_proposal)
    output = tmp_path / "decoded"
    assert decode(generated / "patch.png", output) == 0
    assert (output / "recovered.bin").read_bytes() == (generated / "payload.bin").read_bytes()
    report = json.loads((output / "report.json").read_text())
    assert any("rejected invalid geometry" in event["message"] for event in report["events"])
    attempt = report["attempts"][-1]
    assert attempt["pose"] == report["pose"]
    assert attempt["aperture"] == report["aperture"]


def test_missing_known_samples_are_excluded_from_calibration(
    tmp_path: Path, generated: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _, _, reference = format_parts()
    missing = np.flatnonzero(reference >= 0)[:8]
    original_samples = acquire.cell_samples
    import decode as decoder

    original_fit = decoder.calibrate.fit_window_calibration
    fitted = []

    def samples_with_missing(*args, **kwargs):
        means, observed = original_samples(*args, **kwargs)
        means[missing] = 1  # White outside-image fill must not become a label.
        observed[missing] = False
        return means, observed

    def check_fit(scores, labels, cells):
        assert (labels[missing] == -1).all()
        fitted.append(True)
        return original_fit(scores, labels, cells)

    monkeypatch.setattr(acquire, "cell_samples", samples_with_missing)
    monkeypatch.setattr(decoder.calibrate, "fit_window_calibration", check_fit)
    output = tmp_path / "decoded"
    assert decode(generated / "patch.png", output) == 0
    assert fitted
    assert (output / "recovered.bin").read_bytes() == (generated / "payload.bin").read_bytes()


def test_unreadable_verification_file_preserves_certified_payload(
    tmp_path: Path, generated: Path,
) -> None:
    output = tmp_path / "decoded"
    assert decode(generated / "patch.png", output, verify=tmp_path / "missing.bin") == 3
    report = json.loads((output / "report.json").read_text())
    assert report["status"] == "verification_failed"
    assert report["verification_error"]
    assert report["attempts"][-1]["crc_ok"]
    assert (output / "recovered.bin").read_bytes() == (generated / "payload.bin").read_bytes()


def test_palette_transparency_is_composited_over_white(tmp_path: Path) -> None:
    pixels = np.zeros((100, 100), dtype=np.uint8)
    pixels[40:60, 40:60] = 1
    image = Image.fromarray(pixels).convert("P")
    image.putpalette([0, 0, 0] * 256)  # Both entries black; entry 0 transparent.
    source = tmp_path / "transparent.png"
    image.save(source, transparency=0)
    grey, rgb = acquire.read_image(source, 1800, False, 0, lambda *_: None)
    assert grey[0, 0] == 1
    assert (rgb[0, 0] == 255).all()
    assert grey[50, 50] == 0


def test_cli_reports_output_creation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    import decode as decoder

    parent_file = tmp_path / "file"
    parent_file.write_text("not a directory")
    monkeypatch.setattr(sys, "argv", [
        "decode.py", "unused.png", "--out", str(parent_file / "output"),
    ])
    with pytest.raises(SystemExit) as exc:
        decoder.main()
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert "error:" in error
    assert "Traceback" not in error
