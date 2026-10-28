from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image

from holo.qualification import color_distort
from holo.qualification.color_distort import (
    DistortionParameters,
    distort_tiff,
    distort_with_parameters,
    profile_parameters,
)


def _write_source(
    path: Path,
    *,
    mode: str = "RGB",
    dpi: int = 600,
) -> np.ndarray:
    if mode == "RGB":
        pixels = np.full((30, 40, 3), 255, dtype=np.uint8)
        pixels[4:26, 5:35] = (35, 120, 210)
        pixels[8:22:2, 9:31:3] = (0, 0, 0)
    else:
        pixels = np.full((30, 40), 127, dtype=np.uint8)
    Image.fromarray(pixels, mode=mode).save(
        path,
        format="TIFF",
        compression="tiff_deflate",
        dpi=(dpi, dpi),
    )
    return pixels


def _assert_tiff(
    path: Path,
    *,
    shape: tuple[int, int, int],
    dpi: int,
) -> np.ndarray:
    with tifffile.TiffFile(path) as source:
        page = source.pages[0]
        assert len(source.pages) == 1
        assert page.shape == shape
        assert page.dtype == np.uint8
        assert page.samplesperpixel == 3
        assert page.tags["XResolution"].value == (dpi, 1)
        assert page.tags["YResolution"].value == (dpi, 1)
        assert page.tags["ResolutionUnit"].value == 2
    return tifffile.imread(path)


def test_nominal_profile_is_deterministic_1200_tiff_in_tiff_out(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    first = tmp_path / "first.tif"
    replay = tmp_path / "replay.tif"
    _write_source(source)

    assert distort_tiff(
        source,
        first,
        profile="nominal",
        seed=20260727,
        output_dpi=1200,
    ) == first
    distort_tiff(
        source,
        replay,
        profile="nominal",
        seed=20260727,
        output_dpi=1200,
    )

    first_pixels = _assert_tiff(
        first, shape=(180, 188, 3), dpi=1200)
    replay_pixels = _assert_tiff(
        replay, shape=(180, 188, 3), dpi=1200)
    assert np.array_equal(first_pixels, replay_pixels)
    assert first.read_bytes() == replay.read_bytes()
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "first.tif",
        "replay.tif",
        "source.tif",
    ]


def test_stress_profile_cli_writes_real_4800_raster(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.tif"
    output = tmp_path / "stress.tif"
    _write_source(source)

    assert color_distort.main([
        str(source),
        str(output),
        "--profile",
        "stress",
        "--seed",
        "17",
        "--output-dpi",
        "4800",
    ]) == 0

    _assert_tiff(output, shape=(1040, 1248, 3), dpi=4800)
    assert "(stress, 4800 dpi)" in capsys.readouterr().out


def test_strip_written_4800_resampling_matches_one_pass(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    output = tmp_path / "output.tif"
    _write_source(source)

    distort_with_parameters(
        source,
        output,
        DistortionParameters(seed=0),
        output_dpi=4800,
    )
    with Image.open(source) as image:
        expected_image = image.transform(
            (image.width * 8, image.height * 8),
            Image.Transform.AFFINE,
            (1 / 8, 0.0, 0.0, 0.0, 1 / 8, 0.0),
            resample=Image.Resampling.BICUBIC,
        )
        expected = np.asarray(expected_image, dtype=np.uint8).copy()
        expected_image.close()

    assert np.array_equal(tifffile.imread(output), expected)


def test_cli_explicit_option_starts_from_plain_transform(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    output = tmp_path / "cli.tif"
    expected = tmp_path / "expected.tif"
    _write_source(source)

    assert color_distort.main([
        str(source),
        str(output),
        "--output-dpi", "1200",
        "--blur", "0.5",
    ]) == 0
    distort_with_parameters(
        source,
        expected,
        DistortionParameters(seed=0, blur_radius_dots=0.5),
        output_dpi=1200,
    )

    _assert_tiff(output, shape=(60, 80, 3), dpi=1200)
    assert output.read_bytes() == expected.read_bytes()
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "cli.tif",
        "expected.tif",
        "source.tif",
    ]


def test_cli_explicit_option_overrides_only_its_profile_value(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    output = tmp_path / "cli.tif"
    expected = tmp_path / "expected.tif"
    _write_source(source)

    assert color_distort.main([
        str(source),
        str(output),
        "--profile", "nominal",
        "--seed", "17",
        "--dropout", "0",
    ]) == 0
    parameters = replace(
        profile_parameters("nominal", 17, width=40, height=30),
        dropout_probability=0.0,
    )
    distort_with_parameters(
        source, expected, parameters, output_dpi=1200)

    assert output.read_bytes() == expected.read_bytes()


def test_explicit_options_do_not_modify_a_device_profile(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    _write_discrete_source(source)

    with pytest.raises(SystemExit):
        color_distort.main([
            str(source),
            str(tmp_path / "out.tif"),
            "--profile", "hp-m281-flatbed-cmy",
            "--seed", "17",
            "--blur", "1",
        ])


def test_explicit_parameters_preserve_transform_algorithm(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    _write_source(source)
    parameters = DistortionParameters(
        seed=123,
        shear_xy=(0.08, -0.025),
        translation_xy=(1.5, -0.5),
        canvas_margin_yx=(5, 7),
        crop_yxhw=(3, 4, 34, 46),
        dropout_probability=0.20,
        speckle_probability=0.08,
        speckle_rgb=(10, 20, 30),
        blur_radius_dots=0.55,
        noise_std_rgb=(3.0, 4.0, 5.0),
    )
    first = tmp_path / "first.tif"
    replay = tmp_path / "replay.tif"
    changed = tmp_path / "changed.tif"

    distort_with_parameters(
        source, first, parameters, output_dpi=1200)
    distort_with_parameters(
        source, replay, parameters, output_dpi=1200)
    distort_with_parameters(
        source,
        changed,
        DistortionParameters(
            seed=124,
            shear_xy=parameters.shear_xy,
            translation_xy=parameters.translation_xy,
            canvas_margin_yx=parameters.canvas_margin_yx,
            crop_yxhw=parameters.crop_yxhw,
            dropout_probability=parameters.dropout_probability,
            speckle_probability=parameters.speckle_probability,
            speckle_rgb=parameters.speckle_rgb,
            blur_radius_dots=parameters.blur_radius_dots,
            noise_std_rgb=parameters.noise_std_rgb,
        ),
        output_dpi=1200,
    )

    first_pixels = _assert_tiff(
        first, shape=(68, 92, 3), dpi=1200)
    assert np.array_equal(first_pixels, tifffile.imread(replay))
    assert not np.array_equal(first_pixels, tifffile.imread(changed))


def test_dropout_and_speckle_use_original_source_eligibility() -> None:
    pixels = np.asarray(
        [[[0, 0, 0], [255, 255, 255]]],
        dtype=np.uint8,
    )
    color_distort._apply_source_defects(
        pixels,
        DistortionParameters(
            seed=1,
            dropout_probability=1.0,
            speckle_probability=1.0,
            speckle_rgb=(10, 20, 30),
        ),
    )

    assert np.array_equal(
        pixels,
        np.asarray(
            [[[255, 255, 255], [10, 20, 30]]],
            dtype=np.uint8,
        ),
    )


@pytest.mark.parametrize(
    ("keywords", "match"),
    (
        ({"seed": -1}, "unsigned"),
        ({"seed": 0, "dropout_probability": 1.1}, r"\[0, 1\]"),
        ({"seed": 0, "canvas_margin_yx": (-1, 0)}, "integers"),
        ({"seed": 0, "crop_yxhw": (0, 0, 0, 4)}, "positive"),
        ({"seed": 0, "noise_std_rgb": (0.0, -1.0, 0.0)}, "nonnegative"),
        ({"seed": 0, "shear_xy": (1.0, 1.0)}, "singular"),
    ),
)
def test_parameters_refuse_malformed_values(
    keywords: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        DistortionParameters(**keywords)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("keywords", "match"),
    (
        ({"profile": "nominal", "seed": True, "width": 40, "height": 30},
         "unsigned"),
        ({"profile": "nominal", "seed": 1, "width": 40.5, "height": 30},
         "width"),
        ({"profile": "nominal", "seed": 1, "width": 40, "height": False},
         "height"),
        ({"profile": "unknown", "seed": 1, "width": 40, "height": 30},
         "unknown"),
    ),
)
def test_profile_parameters_are_strict(
    keywords: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        profile_parameters(**keywords)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mode", "dpi", "match"),
    (
        ("L", 600, "RGB"),
        ("RGB", 300, "600-dpi"),
    ),
)
def test_tool_rejects_wrong_input_footing(
    tmp_path: Path,
    mode: str,
    dpi: int,
    match: str,
) -> None:
    source = tmp_path / "source.tif"
    _write_source(source, mode=mode, dpi=dpi)
    with pytest.raises(ValueError, match=match):
        distort_tiff(
            source,
            tmp_path / "out.tif",
            profile="nominal",
            seed=1,
        )


def test_tool_rejects_non_tiff_and_multiframe_tiff(tmp_path: Path) -> None:
    pixels = np.full((8, 9, 3), 127, dtype=np.uint8)
    png = tmp_path / "source.png"
    Image.fromarray(pixels, mode="RGB").save(png, dpi=(600, 600))
    with pytest.raises(ValueError, match="TIFF file"):
        distort_tiff(
            png, tmp_path / "png-out.tif", profile="nominal", seed=1)

    multi = tmp_path / "multi.tif"
    frames = [
        Image.fromarray(pixels, mode="RGB"),
        Image.fromarray(255 - pixels, mode="RGB"),
    ]
    frames[0].save(
        multi,
        format="TIFF",
        save_all=True,
        append_images=frames[1:],
        dpi=(600, 600),
    )
    for frame in frames:
        frame.close()
    with pytest.raises(ValueError, match="exactly one frame"):
        distort_tiff(
            multi, tmp_path / "multi-out.tif", profile="nominal", seed=1)


def test_tool_refuses_overwrite_and_dangling_symlink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    output = tmp_path / "out.tif"
    _write_source(source)
    output.write_bytes(b"foreign")
    with pytest.raises(FileExistsError):
        distort_tiff(source, output, profile="nominal", seed=1)
    assert output.read_bytes() == b"foreign"

    output.unlink()
    external = tmp_path / "external.tif"
    output.symlink_to(external)
    with pytest.raises(FileExistsError):
        distort_tiff(source, output, profile="nominal", seed=1)
    assert output.is_symlink()
    assert not external.exists()


def test_failure_leaves_no_output_or_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.tif"
    output = tmp_path / "out.tif"
    _write_source(source)

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected")

    monkeypatch.setattr(color_distort, "_write_sampled_tiff", fail)
    with pytest.raises(RuntimeError, match="injected"):
        distort_tiff(source, output, profile="nominal", seed=1)
    assert not output.exists()
    assert not list(tmp_path.glob(".holo-color-distort-*.staging"))


def _write_discrete_source(path: Path) -> None:
    rng = np.random.default_rng(20260727)
    planes = rng.integers(0, 2, (3, 32, 36), dtype=np.uint8)
    pixels = np.moveaxis(255 * (1 - planes), 0, 2).astype(np.uint8)
    Image.fromarray(pixels, mode="RGB").save(
        path,
        format="TIFF",
        compression="tiff_deflate",
        dpi=(600, 600),
    )


def test_hp_m281_flatbed_profile_is_deterministic_and_fixed_1200(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    first = tmp_path / "first.tif"
    replay = tmp_path / "replay.tif"
    changed = tmp_path / "changed.tif"
    _write_discrete_source(source)

    distort_tiff(
        source, first, profile="hp-m281-flatbed-cmy", seed=17)
    distort_tiff(
        source, replay, profile="hp-m281-flatbed-cmy", seed=17)
    distort_tiff(
        source, changed, profile="hp-m281-flatbed-cmy", seed=18)

    first_pixels = _assert_tiff(
        first, shape=(64, 72, 3), dpi=1200)
    assert np.array_equal(first_pixels, tifffile.imread(replay))
    assert not np.array_equal(first_pixels, tifffile.imread(changed))
    with pytest.raises(ValueError, match="only 1200"):
        distort_tiff(
            source,
            tmp_path / "bad-dpi.tif",
            profile="hp-m281-flatbed-cmy",
            seed=17,
            output_dpi=4800,
        )


def test_hp_profile_passes_exact_planes_and_parameters_to_simulator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import paperholo.channel.simulator as simulator

    source = tmp_path / "source.tif"
    output = tmp_path / "output.tif"
    _write_discrete_source(source)
    source_pixels = tifffile.imread(source)
    seen: dict[str, object] = {}

    def fake_print_scan_cmy(
        planes: np.ndarray,
        parameters: simulator.ChannelParams,
    ) -> np.ndarray:
        seen["planes"] = planes.copy()
        seen["parameters"] = parameters
        return np.asarray(
            [[[-0.1, 0.5, 1.1], [0.0, 0.25, 1.0]]],
            dtype=np.float64,
        )

    monkeypatch.setattr(
        simulator, "print_scan_cmy", fake_print_scan_cmy)
    distort_tiff(
        source, output, profile="hp-m281-flatbed-cmy", seed=17)

    assert np.array_equal(
        seen["planes"],
        np.moveaxis(source_pixels < 128, 2, 0).astype(np.uint8),
    )
    parameters = seen["parameters"]
    assert isinstance(parameters, simulator.ChannelParams)
    assert parameters.seed == 17
    assert parameters.scan_seed == color_distort._domain_seed(
        17, "hp-m281-flatbed-scan")
    assert parameters.emission == "screened_composite"
    assert parameters.geometry is True
    assert np.array_equal(
        _assert_tiff(output, shape=(1, 2, 3), dpi=1200),
        np.asarray([[[0, 128, 255], [0, 64, 255]]], dtype=np.uint8),
    )


def test_hp_profile_failure_leaves_no_output_or_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import paperholo.channel.simulator as simulator

    source = tmp_path / "source.tif"
    output = tmp_path / "output.tif"
    _write_discrete_source(source)

    def fail(*args: object, **kwargs: object) -> np.ndarray:
        raise RuntimeError("injected")

    monkeypatch.setattr(simulator, "print_scan_cmy", fail)
    with pytest.raises(RuntimeError, match="injected"):
        distort_tiff(
            source, output, profile="hp-m281-flatbed-cmy", seed=17)
    assert not output.exists()
    assert not list(tmp_path.glob(".holo-color-distort-*.staging"))


def test_hp_profile_rejects_more_than_eight_colors(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    pixels = np.arange(20 * 24 * 3, dtype=np.uint8).reshape(20, 24, 3)
    Image.fromarray(pixels, mode="RGB").save(
        source, format="TIFF", dpi=(600, 600))
    with pytest.raises(ValueError, match="at most eight"):
        distort_tiff(
            source,
            tmp_path / "out.tif",
            profile="hp-m281-flatbed-cmy",
            seed=1,
        )


@pytest.mark.parametrize(
    ("colors", "match"),
    (
        (((127, 255, 255),), "ambiguous"),
        (((0, 255, 255), (1, 254, 254)), "unique"),
    ),
)
def test_hp_profile_rejects_nonseparable_palette(
    tmp_path: Path,
    colors: tuple[tuple[int, int, int], ...],
    match: str,
) -> None:
    source = tmp_path / "source.tif"
    pixels = np.empty((20, 24, 3), dtype=np.uint8)
    for x in range(pixels.shape[1]):
        pixels[:, x] = colors[x % len(colors)]
    Image.fromarray(pixels, mode="RGB").save(
        source, format="TIFF", dpi=(600, 600))

    with pytest.raises(ValueError, match=match):
        distort_tiff(
            source,
            tmp_path / "out.tif",
            profile="hp-m281-flatbed-cmy",
            seed=1,
        )


def _write_bw_source(path: Path) -> np.ndarray:
    """A black/white page whose ink is gs's CMYK-K proof value (35,31,32)."""
    rng = np.random.default_rng(20260802)
    bits = rng.integers(0, 2, (32, 36), dtype=np.uint8)
    pixels = np.where(
        bits[..., None] == 1,
        np.asarray((35, 31, 32), dtype=np.uint8),
        np.asarray((255, 255, 255), dtype=np.uint8),
    ).astype(np.uint8)
    Image.fromarray(pixels, mode="RGB").save(
        path,
        format="TIFF",
        compression="tiff_deflate",
        dpi=(600, 600),
    )
    return bits


def _assert_gray_tiff(
    path: Path,
    *,
    shape: tuple[int, int],
    dpi: int,
) -> np.ndarray:
    with tifffile.TiffFile(path) as source:
        page = source.pages[0]
        assert len(source.pages) == 1
        assert page.shape == shape
        assert page.dtype == np.uint8
        assert page.samplesperpixel == 1
        assert page.photometric == tifffile.PHOTOMETRIC.MINISBLACK
        assert page.tags["XResolution"].value == (dpi, 1)
        assert page.tags["YResolution"].value == (dpi, 1)
        assert page.tags["ResolutionUnit"].value == 2
    return tifffile.imread(path)


def test_hp_k_profile_is_deterministic_grayscale_and_fixed_1200(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    first = tmp_path / "first.tif"
    replay = tmp_path / "replay.tif"
    changed = tmp_path / "changed.tif"
    _write_bw_source(source)

    distort_tiff(
        source, first, profile="hp-m281-flatbed-k", seed=17)
    distort_tiff(
        source, replay, profile="hp-m281-flatbed-k", seed=17)
    distort_tiff(
        source, changed, profile="hp-m281-flatbed-k", seed=18)

    first_pixels = _assert_gray_tiff(
        first, shape=(64, 72), dpi=1200)
    assert np.array_equal(first_pixels, tifffile.imread(replay))
    assert not np.array_equal(first_pixels, tifffile.imread(changed))
    with pytest.raises(ValueError, match="only 1200"):
        distort_tiff(
            source,
            tmp_path / "bad-dpi.tif",
            profile="hp-m281-flatbed-k",
            seed=17,
            output_dpi=4800,
        )


def test_hp_k_profile_passes_exact_plane_and_parameters_to_simulator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import paperholo.channel.simulator as simulator

    source = tmp_path / "source.tif"
    output = tmp_path / "output.tif"
    bits = _write_bw_source(source)
    seen: dict[str, object] = {}

    def fake_print_scan(
        plane_bits: np.ndarray,
        parameters: simulator.ChannelParams,
    ) -> np.ndarray:
        seen["plane_bits"] = plane_bits.copy()
        seen["parameters"] = parameters
        return np.asarray(
            [[-0.1, 0.5], [1.1, 0.25]],
            dtype=np.float64,
        )

    monkeypatch.setattr(simulator, "print_scan", fake_print_scan)
    distort_tiff(
        source, output, profile="hp-m281-flatbed-k", seed=17)

    assert np.array_equal(seen["plane_bits"], bits)
    parameters = seen["parameters"]
    assert isinstance(parameters, simulator.ChannelParams)
    assert parameters.seed == 17
    assert parameters.scan_seed == color_distort._domain_seed(
        17, "hp-m281-flatbed-k-scan")
    assert parameters.plane == "K"
    assert parameters.emission == "clean_mask"
    assert parameters.geometry is True
    assert np.array_equal(
        _assert_gray_tiff(output, shape=(2, 2), dpi=1200),
        np.asarray([[0, 128], [255, 64]], dtype=np.uint8),
    )


def test_hp_k_profile_rejects_colored_ink(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    _write_discrete_source(source)
    with pytest.raises(ValueError, match="black/white"):
        distort_tiff(
            source,
            tmp_path / "out.tif",
            profile="hp-m281-flatbed-k",
            seed=1,
        )


@pytest.mark.parametrize(
    ("profile", "seed", "dpi", "match"),
    (
        ("missing", 1, 1200, "unknown profile"),
        ("nominal", -1, 1200, "unsigned"),
        ("nominal", True, 1200, "unsigned"),
        ("nominal", 1, 600, "1200 or 4800"),
        ("nominal", 1, True, "1200 or 4800"),
    ),
)
def test_tool_rejects_invalid_controls(
    tmp_path: Path,
    profile: str,
    seed: object,
    dpi: object,
    match: str,
) -> None:
    source = tmp_path / "source.tif"
    _write_source(source)
    with pytest.raises(ValueError, match=match):
        distort_tiff(
            source,
            tmp_path / "out.tif",
            profile=profile,
            seed=seed,  # type: ignore[arg-type]
            output_dpi=dpi,  # type: ignore[arg-type]
        )


def test_tool_refuses_a_non_tiff_output_name(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    output = tmp_path / "not-a-tiff.png"
    _write_source(source)

    with pytest.raises(ValueError, match=r"\.tif"):
        distort_with_parameters(
            source,
            output,
            DistortionParameters(seed=0),
            output_dpi=1200,
        )
    assert not output.exists()
