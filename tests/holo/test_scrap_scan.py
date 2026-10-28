from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import tifffile

from holo.qualification import scrap_scan
from holo.qualification.scrap_scan import (
    ScrapScanParameters,
    generate_scrap_scans,
    plan_scrap_page,
)


def _write_source(
    path: Path,
    *,
    rgb: bool = True,
    dpi: int = 600,
) -> np.ndarray:
    y, x = np.indices((180, 240), dtype=np.uint16)
    gray = ((3 * x + 5 * y) % 190 + 20).astype(np.uint8)
    if rgb:
        pixels = np.stack(
            (gray, np.roll(gray, 17, axis=1), np.roll(gray, 11, axis=0)),
            axis=2,
        )
        photometric = "rgb"
    else:
        pixels = gray
        photometric = "minisblack"
    tifffile.imwrite(
        path,
        pixels,
        photometric=photometric,
        compression="deflate",
        resolution=(dpi, dpi),
        resolutionunit="INCH",
    )
    return pixels


def _parameters(**overrides: object) -> ScrapScanParameters:
    values: dict[str, object] = {
        "seed": 20260727,
        "pages": 1,
        "scraps_per_page": 5,
        "size_mm": (0.7, 2.0),
        "aspect_ratio": (0.45, 1.0),
        "tear_mm": 0.05,
        "fold_probability": 0.5,
        "flap_probability": 0.5,
        "shadow_strength": 0.12,
    }
    values.update(overrides)
    return ScrapScanParameters(**values)  # type: ignore[arg-type]


def _assert_tiff(
    path: Path,
    *,
    shape: tuple[int, ...],
    dpi: int = 600,
) -> np.ndarray:
    with tifffile.TiffFile(path) as source:
        assert len(source.pages) == 1
        page = source.pages[0]
        assert page.shape == shape
        assert page.dtype == np.uint8
        assert page.compression == 1
        assert page.tags["XResolution"].value == (dpi, 1)
        assert page.tags["YResolution"].value == (dpi, 1)
        assert page.tags["ResolutionUnit"].value == 2
    return tifffile.imread(path)


def test_multiple_pages_are_deterministic_tiff_in_tiff_out(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tiff"
    _write_source(source)
    first = _parameters(pages=2)

    outputs = generate_scrap_scans(
        source, tmp_path / "scan.tiff", first)
    replays = generate_scrap_scans(
        source, tmp_path / "replay.tiff", first)

    assert tuple(path.name for path in outputs) == (
        "scan-001.tiff",
        "scan-002.tiff",
    )
    assert tuple(path.name for path in replays) == (
        "replay-001.tiff",
        "replay-002.tiff",
    )
    for output, replay in zip(outputs, replays, strict=True):
        actual = _assert_tiff(output, shape=(180, 240, 3))
        repeated = _assert_tiff(replay, shape=(180, 240, 3))
        assert np.array_equal(actual, repeated)
        assert np.count_nonzero(actual < 250) > 2000


def test_plan_has_exact_scrap_count_varied_sizes_and_torn_contours() -> None:
    parameters = _parameters(
        scraps_per_page=18,
        fold_probability=1.0,
        flap_probability=1.0,
    )
    plans = plan_scrap_page(
        (1800, 2400, 3), 600.0, parameters, page_index=0)

    assert len(plans) == 18
    sizes = {(plan.source_yxhw[2], plan.source_yxhw[3])
             for plan in plans}
    assert len(sizes) > 10
    assert all(len(plan.contour_xy) >= 40 for plan in plans)
    assert all(plan.fold_normal_xy is not None for plan in plans)
    assert all(plan.folded_back for plan in plans)
    assert all(
        0 <= plan.source_yxhw[0]
        <= 1800 - plan.source_yxhw[2]
        and 0 <= plan.source_yxhw[1]
        <= 2400 - plan.source_yxhw[3]
        for plan in plans
    )
    gap = 600.0 / 25.4
    bounds = [scrap_scan._content_bounds(plan) for plan in plans]
    assert all(
        scrap_scan._separated(first, second, gap)
        for index, first in enumerate(bounds)
        for second in bounds[index + 1:]
    )


def test_default_a4_plan_is_feasible_and_keeps_shadows_bounded() -> None:
    parameters = ScrapScanParameters(
        seed=20260728,
        shadow_strength=1.0,
    )
    plans = plan_scrap_page(
        (7016, 4960, 3), 600.0, parameters, page_index=0)

    assert len(plans) == parameters.scraps_per_page
    assert all(0.0 <= plan.shadow_strength <= 1.0 for plan in plans)
    gap = 600.0 / 25.4
    bounds = [scrap_scan._content_bounds(plan) for plan in plans]
    assert all(
        scrap_scan._separated(first, second, gap)
        for index, first in enumerate(bounds)
        for second in bounds[index + 1:]
    )


def test_grayscale_mode_and_dpi_are_preserved(tmp_path: Path) -> None:
    source = tmp_path / "gray.tif"
    _write_source(source, rgb=False, dpi=300)
    output, = generate_scrap_scans(
        source,
        tmp_path / "scraps.tif",
        _parameters(
            size_mm=(0.7, 1.5),
            tear_mm=0.05,
        ),
    )

    actual = _assert_tiff(output, shape=(180, 240), dpi=300)
    assert actual.ndim == 2
    assert np.count_nonzero(actual < 250) > 200


def test_compressed_4800_dpi_source_stays_4800_dpi(
    tmp_path: Path,
) -> None:
    source = tmp_path / "r4800.tif"
    _write_source(source, dpi=4800)
    output, = generate_scrap_scans(
        source,
        tmp_path / "scrap-r4800.tif",
        _parameters(
            scraps_per_page=1,
            size_mm=(0.10, 0.45),
            tear_mm=0.02,
        ),
    )

    actual = _assert_tiff(output, shape=(180, 240, 3), dpi=4800)
    assert np.count_nonzero(actual < 250) > 100


def test_different_seed_changes_geometry(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    _write_source(source)
    first, = generate_scrap_scans(
        source, tmp_path / "first.tif", _parameters(seed=1))
    second, = generate_scrap_scans(
        source, tmp_path / "second.tif", _parameters(seed=2))

    assert not np.array_equal(
        tifffile.imread(first), tifffile.imread(second))


def test_rendering_work_is_bounded_by_stripe_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.tif"
    _write_source(source)
    heights: list[int] = []
    original = scrap_scan._sample_source

    def observe(
        pixels: np.ndarray,
        plan: scrap_scan.ScrapPlan,
        local_y: np.ndarray,
        local_x: np.ndarray,
    ) -> np.ndarray:
        heights.append(local_y.shape[0])
        return original(pixels, plan, local_y, local_x)

    monkeypatch.setattr(scrap_scan, "_STRIPE_ROWS", 7)
    monkeypatch.setattr(scrap_scan, "_sample_source", observe)
    generate_scrap_scans(
        source, tmp_path / "bounded.tif", _parameters())

    assert heights
    assert max(heights) <= 7


def test_collection_failure_publishes_nothing_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.tif"
    _write_source(source)
    original = scrap_scan._write_page
    calls = 0

    def fail_second(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected")
        original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(scrap_scan, "_write_page", fail_second)
    with pytest.raises(RuntimeError, match="injected"):
        generate_scrap_scans(
            source,
            tmp_path / "collection.tif",
            _parameters(pages=2),
        )

    assert not list(tmp_path.glob("collection-*.tif"))
    assert not list(tmp_path.glob(".holo-scrap-scan-*"))


def test_source_open_failure_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.tif"
    _write_source(source)

    def fail(_path: Path) -> np.ndarray:
        raise RuntimeError("injected source open failure")

    monkeypatch.setattr(scrap_scan, "_open_source", fail)
    with pytest.raises(RuntimeError, match="injected source open failure"):
        generate_scrap_scans(
            source, tmp_path / "output.tif", _parameters())

    assert not (tmp_path / "output.tif").exists()
    assert not list(tmp_path.glob(".holo-scrap-scan-*"))


def test_refuses_overwrite_before_rendering(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    output = tmp_path / "output.tif"
    _write_source(source)
    output.write_bytes(b"owned")

    with pytest.raises(FileExistsError):
        generate_scrap_scans(source, output, _parameters())

    assert output.read_bytes() == b"owned"


def test_refuses_impossible_nonoverlap_request() -> None:
    with pytest.raises(ValueError, match="without overlap"):
        plan_scrap_page(
            (100, 100, 3),
            100.0,
            ScrapScanParameters(
                seed=3,
                scraps_per_page=4,
                size_mm=(20.0, 20.0),
                aspect_ratio=(1.0, 1.0),
            ),
            page_index=0,
        )


@pytest.mark.parametrize(
    ("keywords", "match"),
    (
        ({"seed": -1}, "unsigned"),
        ({"pages": 0}, "positive integer"),
        ({"scraps_per_page": True}, "positive integer"),
        ({"size_mm": (5.0, 4.0)}, "increasing"),
        ({"aspect_ratio": (0.5, 1.2)}, "must not exceed"),
        ({"tear_mm": -0.1}, "nonnegative"),
        ({"fold_probability": 1.1}, r"\[0, 1\]"),
        ({"flap_probability": -0.1}, "nonnegative"),
        ({"shadow_strength": float("nan")}, "finite"),
    ),
)
def test_parameters_refuse_malformed_values(
    keywords: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        ScrapScanParameters(**keywords)  # type: ignore[arg-type]


def test_cli_reports_numbered_outputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.tif"
    _write_source(source)

    assert scrap_scan.main([
        str(source),
        str(tmp_path / "cli.tiff"),
        "--pages", "2",
        "--scraps", "3",
        "--seed", "9",
        "--size-mm", "0.6", "1.5",
        "--tear-mm", "0.05",
    ]) == 0

    reported = capsys.readouterr().out.splitlines()
    assert [Path(value).name for value in reported] == [
        "cli-001.tiff",
        "cli-002.tiff",
    ]


def test_refuses_non_tiff_and_missing_or_nonsquare_density(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "source.png"
    fake.write_bytes(b"not a TIFF")
    with pytest.raises(ValueError, match="TIFF"):
        generate_scrap_scans(
            fake, tmp_path / "out.tif", _parameters())

    no_density = tmp_path / "no-density.tif"
    tifffile.imwrite(
        no_density,
        np.zeros((20, 30), np.uint8),
        photometric="minisblack",
    )
    with pytest.raises(ValueError, match="density"):
        generate_scrap_scans(
            no_density, tmp_path / "out.tif", _parameters())

    nonsquare = tmp_path / "nonsquare.tif"
    tifffile.imwrite(
        nonsquare,
        np.zeros((20, 30), np.uint8),
        photometric="minisblack",
        resolution=(300, 600),
        resolutionunit="INCH",
    )
    with pytest.raises(ValueError, match="square"):
        generate_scrap_scans(
            nonsquare, tmp_path / "out.tif", _parameters())


def test_refuses_ycbcr_samples_instead_of_mislabeling_them_rgb(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ycbcr.tif"
    pixels = np.empty((20, 30, 3), np.uint8)
    pixels[...] = (100, 150, 200)
    tifffile.imwrite(
        source,
        pixels,
        photometric="ycbcr",
        compression=None,
        subsampling=(1, 1),
        resolution=(600, 600),
        resolutionunit="INCH",
    )

    with pytest.raises(ValueError, match="RGB samples"):
        generate_scrap_scans(
            source, tmp_path / "out.tif", _parameters())
