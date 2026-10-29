"""End-to-end toy checks: arbitrary data, optics, corruption and rejection."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from PIL import Image
from scipy import ndimage
import pytest

from common import format_parts
from generate import generate
from decode import decode
from acquire import homography, project


def image_array(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image).copy()


@pytest.mark.parametrize("mode", ["page", "perspective", "damaged"])
def test_arbitrary_payload(tmp_path: Path, mode: str) -> None:
    rng = np.random.default_rng(7391)
    payload = rng.bytes(263)
    generated = tmp_path / "generated"
    generate(payload, generated)
    source = generated / "tile.png"
    if mode != "page":
        image = image_array(generated / "patch.png").astype(float) / 255
        tile = image[60:1020, 60:1020]
        if mode == "damaged":
            # Flip unknown cells only, forcing genuine error correction.
            _, _, _, _, reference = format_parts()
            for flat in rng.choice(np.flatnonzero(reference < 0), 80, replace=False):
                y, x = divmod(int(flat), 64)
                bounds = np.s_[y * 15 : (y + 1) * 15, x * 15 : (x + 1) * 15]
                tile[bounds] = 1 - tile[bounds]
        # Perspective plus non-right-angle rotation; mirror one case too.
        quad = np.array([[210, 65], [765, 225], [675, 805], [55, 590]], float)
        if mode == "damaged":
            quad = quad[[1, 0, 3, 2]]
        yy, xx = np.indices((870, 870))
        cell = project(np.linalg.inv(homography(quad)), np.stack((xx, yy), axis=-1))
        warped = ndimage.map_coordinates(
            tile, [cell[..., 1] * 15 - .5, cell[..., 0] * 15 - .5],
            order=1, cval=1.,
        )
        warped = ndimage.gaussian_filter(warped, .65)
        warped = np.clip(
            warped * (.75 + .2 * xx / 870) + rng.normal(0, .012, warped.shape), 0, 1,
        )
        source = tmp_path / "photo.png"
        Image.fromarray(np.uint8(warped * 255)).save(source)
    out = tmp_path / "decoded"
    assert decode(source, out) == 0
    assert (out / "recovered.bin").read_bytes() == payload
    report = json.loads((out / "report.json").read_text())
    assert report["attempts"][-1]["crc_ok"]
    if mode == "damaged":
        assert report["postdecode_hard_cell_errors"] >= 70
        assert report["attempts"][-1]["n_iters"] > 0


@pytest.mark.parametrize("kind", ["blank", "random"])
def test_reject_nonframe(tmp_path: Path, kind: str) -> None:
    pixels = np.full((720, 720), 255, np.uint8)
    if kind == "random":
        random_cells = np.random.default_rng(7).integers(
            0, 2, (64, 64), dtype=np.uint8,
        ) * 255
        pixels[40:680, 40:680] = np.repeat(np.repeat(random_cells, 10, 0), 10, 1)
    source = tmp_path / "invalid.png"
    Image.fromarray(pixels).save(source)
    out = tmp_path / "decode"
    assert decode(source, out) == 2
    assert not (out / "recovered.bin").exists()
    assert json.loads((out / "report.json").read_text())["status"] == "failed"


def test_length_guard(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly 263"):
        generate(bytes(262), tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_postscript_matches_png(tmp_path: Path) -> None:
    gs = shutil.which("gs")
    if not gs:
        pytest.skip("Ghostscript unavailable")
    generate(bytes(i % 256 for i in range(263)), tmp_path / "generated")
    rendered = tmp_path / "ps.png"
    subprocess.run(
        [gs, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pnggray",
         "-r600", f"-sOutputFile={rendered}", str(tmp_path / "generated/tile.ps")],
        check=True,
    )
    # Ghostscript color management renders DeviceCMYK K as grey 32 here;
    # the exact binary ink mask and physical placement must agree.
    assert np.array_equal(
        image_array(rendered) < 128,
        image_array(tmp_path / "generated/tile.png") < 128,
    )


def test_verification_is_after_recovery(tmp_path: Path) -> None:
    payload = np.random.default_rng(14).bytes(263)
    generate(payload, tmp_path / "generated")
    wrong = tmp_path / "wrong.bin"
    wrong.write_bytes(bytes(263))
    out = tmp_path / "decode"
    assert decode(
        tmp_path / "generated/patch.png", out, verify=wrong,
        flatten_lighting=True, radial_k1=.001,
    ) == 3
    assert (out / "recovered.bin").read_bytes() == payload
    assert json.loads((out / "report.json").read_text())["status"] == "verification_failed"
