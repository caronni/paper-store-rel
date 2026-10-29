"""Illustration contracts: raw bytes, printed geometry and safe CLI failures."""
from __future__ import annotations

import builtins
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image
import pytest

import compare
import generate
from common import PAYLOAD_BYTES


@pytest.fixture(scope="module")
def illustration(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, bytes]:
    try:
        qrcode = compare._load_qrcode()
    except ValueError:
        pytest.skip("optional qrcode illustration dependency unavailable")
    payload = np.random.default_rng(3501).bytes(PAYLOAD_BYTES)
    out = tmp_path_factory.mktemp("qr-comparison") / "output"
    qr_instances = []
    original_make = qrcode.QRCode.make

    def record_make(qr, *args, **kwargs) -> None:
        original_make(qr, *args, **kwargs)
        qr_instances.append(qr)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(qrcode.QRCode, "make", record_make)
        compare.compare(payload, out)

    # Inspect the actual library input: all byte values remain a single byte
    # segment, including NUL and high bytes, with no text conversion or base64.
    assert len(qr_instances) == 1
    qr = qr_instances[0]
    assert len(qr.data_list) == 1
    assert qr.data_list[0].mode == 4  # QR standard's 8-bit byte mode indicator.
    assert qr.data_list[0].data == payload
    assert qr.error_correction == qrcode.constants.ERROR_CORRECT_H
    assert qr.version == 17
    assert qr.modules_count == 85
    return out, payload


def test_comparison_payload_geometry_and_provenance(
    illustration: tuple[Path, bytes],
) -> None:
    out, payload = illustration
    assert (out / "ldpc/payload.bin").read_bytes() == payload
    details = json.loads((out / "comparison.json").read_text())
    assert details["qr_library"] == f"qrcode {importlib.metadata.version('qrcode')}"
    assert details["qr_active_mm"] == pytest.approx(53.975)
    assert details["qr_with_quiet_zone_mm"] == pytest.approx(59.055)
    with Image.open(out / "qr.png") as image:
        assert image.info["dpi"] == pytest.approx((600, 600), abs=0.01)
        qr_pixels = np.asarray(image)
    assert qr_pixels.shape == (1395, 1395)
    quiet_dots = 4 * 15
    assert np.all(qr_pixels[:quiet_dots] == 255)
    assert np.all(qr_pixels[-quiet_dots:] == 255)
    assert np.all(qr_pixels[:, :quiet_dots] == 255)
    assert np.all(qr_pixels[:, -quiet_dots:] == 255)
    assert np.any(qr_pixels[quiet_dots:-quiet_dots, quiet_dots:-quiet_dots] == 0)
    with Image.open(out / "comparison.png") as image:
        artwork = np.asarray(image)
    assert np.array_equal(artwork[510:1905, 1840:3235], qr_pixels)
    with Image.open(out / "ldpc/patch.png") as image:
        assert np.array_equal(artwork[510:1590, 160:1240], np.asarray(image))


def test_comparison_postscript_matches_artwork(
    illustration: tuple[Path, bytes], tmp_path: Path,
) -> None:
    gs = shutil.which("gs")
    if gs is None:
        pytest.skip("Ghostscript unavailable")
    out, _ = illustration
    rendered = tmp_path / "rendered.png"
    subprocess.run(
        [
            gs, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE",
            "-sDEVICE=pnggray", "-r600", f"-sOutputFile={rendered}",
            str(out / "comparison.ps"),
        ],
        check=True,
    )
    with Image.open(out / "comparison.png") as image:
        expected = np.zeros((7016, 4960), dtype=bool)
        expected[2358:4658, 730:4230] = np.asarray(image) < 128
    with Image.open(rendered) as image:
        assert np.array_equal(np.asarray(image) < 128, expected)


@pytest.mark.parametrize("emit", [generate.generate, compare.compare])
def test_emit_preserves_existing_output(emit, tmp_path: Path) -> None:
    out = tmp_path / "existing"
    out.mkdir()
    sentinel = out / "keep.bin"
    sentinel.write_bytes(b"already here")
    with pytest.raises(ValueError, match="already exists"):
        emit(bytes(PAYLOAD_BYTES), out)
    assert sorted(path.name for path in out.iterdir()) == ["keep.bin"]
    assert sentinel.read_bytes() == b"already here"


def test_compare_length_guard(tmp_path: Path) -> None:
    out = tmp_path / "output"
    with pytest.raises(ValueError, match="exactly 263"):
        compare.compare(bytes(PAYLOAD_BYTES - 1), out)
    assert not out.exists()


def test_optional_dependency_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path,
) -> None:
    original_import = builtins.__import__

    def without_qrcode(name: str, *args, **kwargs):
        if name == "qrcode":
            raise ModuleNotFoundError("No module named 'qrcode'", name="qrcode")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_qrcode)
    monkeypatch.setattr(sys, "argv", ["compare.py", "--help"])
    with pytest.raises(SystemExit) as helped:
        compare.main()
    assert helped.value.code == 0
    assert "--payload" in capsys.readouterr().out
    out = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", ["compare.py", "--out", str(out)])
    with pytest.raises(SystemExit) as missing:
        compare.main()
    assert missing.value.code == 2
    assert "pip install" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("inputs", [[], ["payload.bin", "--counting"]])
def test_generator_requires_one_input(
    inputs: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    out = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", ["generate.py", *inputs, "--out", str(out)])
    with pytest.raises(SystemExit) as invalid:
        generate.main()
    assert invalid.value.code == 2
    assert not out.exists()
