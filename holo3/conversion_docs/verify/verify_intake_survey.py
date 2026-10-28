# Wave-2 P1 verify: holo3/plugins/intake.py + holo3/plugins/survey.py
# Oracle: holo2.capture.{scale_space,scan,ingest,lattice,_survey_tensor,survey}
# Run:  cd <checkout> && \
#       PYTHONPATH=.:src:holo2/src env314t/bin/python \
#       _distill/verify/verify_intake_survey.py
from __future__ import annotations

import shutil
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "_distill" / "verify" / "_tmp_intake"

from holo3.format.identity import Family                          # noqa: E402
from holo3.lib import decimate as h3decimate                      # noqa: E402
from holo3.plugins import intake as h3intake                      # noqa: E402
from holo3.plugins import survey as h3survey                      # noqa: E402

from holo2.capture import _survey_tensor as o_tensor              # noqa: E402
from holo2.capture import ingest as o_ingest                      # noqa: E402
from holo2.capture import lattice as o_lattice                    # noqa: E402
from holo2.capture import scale_space as o_scale                  # noqa: E402
from holo2.capture import scan as o_scan                          # noqa: E402
from holo2.capture import survey as o_survey                      # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(f"{name} {detail}")


# --------------------------------------------------------------------------
# 1. ladder + level frames
# --------------------------------------------------------------------------
ACCEPTANCE = [
    ("c2", Fraction(1, 300), 1200.0),
    ("c2", Fraction(1, 300), 2400.0),
    ("c2", Fraction(1, 300), 4800.0),
    ("c3", Fraction(1, 200), 1200.0),
    ("c3", Fraction(1, 200), 2400.0),
    ("c3", Fraction(1, 200), 4800.0),
    ("c1", Fraction(1, 600), 2400.0),
    ("c4", Fraction(1, 150), 2400.0),
    ("c4", Fraction(1, 150), 600.0),
    ("odd", Fraction(1, 400), 2400.0),
]


def test_ladder() -> None:
    print("[1] ladder / native_pixels_per_cell parity")
    for name, pitch, dpi in ACCEPTANCE:
        mine = h3decimate.auto_ppc_levels(dpi, pitch)
        theirs = o_scale.auto_ppc_levels(dpi, pitch)
        check(f"ladder {name}@{dpi:g} {tuple(str(v) for v in mine)}",
              mine == theirs, f"{mine} != {theirs}")
        native_mine = h3decimate.native_pixels_per_cell(dpi, pitch)
        native_theirs = o_scale.native_pixels_per_cell(dpi, pitch)
        check(f"native_ppc {name}@{dpi:g}", native_mine == native_theirs)
    # documented spec examples
    check("c2@2400 -> 2,4,8",
          h3decimate.auto_ppc_levels(2400.0, Fraction(1, 300))
          == (Fraction(2), Fraction(4), Fraction(8)))
    check("c2@4800 -> 2,4,8,16",
          h3decimate.auto_ppc_levels(4800.0, Fraction(1, 300))
          == (Fraction(2), Fraction(4), Fraction(8), Fraction(16)))
    check("c3-cmy7@2400 -> 2,4,6,12",
          h3decimate.auto_ppc_levels(2400.0, Fraction(1, 200))
          == (Fraction(2), Fraction(4), Fraction(6), Fraction(12)))
    check("c3@1200 -> 2,3,6",
          h3decimate.auto_ppc_levels(1200.0, Fraction(1, 200))
          == (Fraction(2), Fraction(3), Fraction(6)))
    # Fraction(str(float)) seam: never Fraction(float)
    check("dpi seam uses Fraction(str(float))",
          h3decimate.as_fraction(0.1) == Fraction(1, 10))
    levels = h3intake.build_levels(2400.0, Fraction(1, 300), (4001, 3003))
    check("levels end at native", levels[-1].scale == 1)
    check("level labels", [lv.label for lv in levels]
          == ["l00-2ppc-600dpi", "l01-4ppc-1200dpi", "l02-8ppc-2400dpi"],
          str([lv.label for lv in levels]))
    check("level shapes",
          [lv.shape_px for lv in levels] == [(1000, 750), (2000, 1501),
                                             (4001, 3003)],
          str([lv.shape_px for lv in levels]))
    frame_levels = h3intake.build_levels(2400.0, Fraction(1, 300), (800, 800))
    coarse = frame_levels[0]
    f_ora = __import__(
        "holo2.capture.footing_raster", fromlist=["FootingFrame"]
    ).FootingFrame.of(coarse.ppc,
                      o_scale.native_pixels_per_cell(2400.0, Fraction(1, 300)),
                      (800, 800))
    check("level_pitch_px == FootingFrame.pitch_px",
          h3intake.level_pitch_px(coarse, 8.0) == f_ora.pitch_px(8.0))
    for extent in [(0, 0, 800, 800), (7, 9, 401, 403), (1, 1, 3, 3),
                   (5, 5, 6, 6)]:
        check(f"level_extent {extent}",
              h3intake.level_extent(coarse, extent) == f_ora.extent(extent))
    check("level_centres == FootingFrame._centres",
          np.array_equal(
              h3intake.level_centres(coarse, np.arange(50, dtype=np.int64)),
              f_ora._centres(np.arange(50, dtype=np.int64))))
    return None


# --------------------------------------------------------------------------
# 2. decimation byte-parity through the intake ladder
# --------------------------------------------------------------------------
def _write_npy_tiff(path: Path, array: np.ndarray) -> None:
    import tifffile
    tifffile.imwrite(path, array)


def test_decimation() -> None:
    print("[2] decimation byte-parity (intake ladder vs holo2 kernels)")
    rng = np.random.default_rng(20260828)
    cases = [
        ("grey", 1, Fraction(1, 300), 2400.0, (600, 517)),
        ("rgb", 3, Fraction(1, 300), 2400.0, (600, 517)),
        ("rgb-c3", 3, Fraction(1, 200), 2400.0, (517, 600)),
        ("rgb-c2-4800", 3, Fraction(1, 300), 4800.0, (400, 411)),
    ]
    for name, channels, pitch, dpi, shape in cases:
        shape_full = shape if channels == 1 else shape + (3,)
        native = rng.integers(0, 256, size=shape_full, dtype=np.uint8)
        path = TMP / f"{name}.tif"
        _write_npy_tiff(path, native)
        for family, label in ((Family.CMY8, "colour"), (Family.K, "k")):
            run_dir = TMP / f"run-{name}-{label}"
            capture, planes, events = h3intake.ingest_capture(
                path, dpi, pitch, family, run_dir)
            check(f"{name}/{label} sha == holo2 _sha256_file",
                  capture.capture_id == o_scan._sha256_file(path))
            check(f"{name}/{label} shape/channels",
                  capture.shape_px == shape and capture.channels == channels)
            check(f"{name}/{label} one CaptureOpen event",
                  len(events) == 1 and events[0].duplicate is False)
            native_index = capture.levels[-1].index
            by_key = {(p.level_index, p.plane): p for p in planes}
            # native planes are the scan channels, byte-identical
            names = ("r", "g", "b") if channels == 3 else ("g",)
            for channel, plane_name in enumerate(names):
                stored = by_key[(native_index, plane_name)].open()
                want = (native if channels == 1 else native[..., channel])
                check(f"{name}/{label} native {plane_name} byte-identical",
                      np.array_equal(np.asarray(stored), np.asarray(want)))
            for level in capture.levels[:-1]:
                transform = o_scale.AreaPixelTransform(level.scale)
                if channels == 1:
                    want = o_scale.area_decimate(native, transform)
                    got = np.asarray(by_key[(level.index, "g")].open())
                    check(f"{name}/{label} l{level.index} g == area_decimate",
                          np.array_equal(got, want))
                elif family is Family.K:
                    want = o_scale.area_decimate(native, transform)
                    got = np.asarray(by_key[(level.index, "y")].open())
                    check(f"{name}/{label} l{level.index} y == 3-D "
                          f"area_decimate (E018 order)",
                          np.array_equal(got, want))
                    # informational: how far luma-then-decimate lands from
                    # the frozen E018 order on this fixture (u8 in: the two
                    # coincide, because a 3-sample u8 mean is exact in both
                    # float32 and float64 before the box stage)
                    factor = transform.source_per_output.numerator
                    luma = o_scan._raw_luma(native)
                    wrong = luma[:want.shape[0] * factor,
                                 :want.shape[1] * factor].reshape(
                        want.shape[0], factor, want.shape[1], factor
                    ).mean(axis=(1, 3)).round().clip(0, 255).astype(np.uint8)
                    print(f"       .. l{level.index} luma-then-decimate "
                          f"differs in {int((wrong != got).sum())} px")
                else:
                    want = o_scale.area_decimate_rgb(native, transform)
                    for channel, plane_name in enumerate(("r", "g", "b")):
                        got = np.asarray(
                            by_key[(level.index, plane_name)].open())
                        check(f"{name}/{label} l{level.index} {plane_name} "
                              f"== area_decimate_rgb",
                              np.array_equal(got, want[..., channel]))
                check(f"{name}/{label} l{level.index} shape",
                      by_key[(level.index,
                              "y" if (channels == 3 and family is Family.K)
                              else ("g" if channels == 1 else "r"))].shape_px
                      == transform.output_shape(shape))
        # platen backing parity
        raster = o_scan.open_capture(native, dpi)
        check(f"{name} platen_backing == holo2 ingest.platen_backing",
              h3intake.platen_backing(native)
              == o_ingest.platen_backing(raster))
        # luma parity: stacked planes vs interleaved
        if channels == 3:
            mine = h3decimate.plane_mean_luma_f32(
                native[..., 0], native[..., 1], native[..., 2])
            check(f"{name} plane-mean luma == interleaved _raw_luma",
                  np.array_equal(mine, o_scan._raw_luma(native))
                  and mine.dtype == np.float32)
    # integer-factor-only refusal (C-10)
    odd = np.zeros((64, 64), np.uint8)
    try:
        h3decimate.area_decimate(
            odd, h3decimate.AreaPixelTransform(Fraction(5, 2)))
        check("non-integer ladder factor refuses", False, "no refusal")
    except ValueError:
        check("non-integer ladder factor refuses", True)
    # PIL route: a PNG carries the same planes as the TIFF route
    from PIL import Image
    rgb = rng.integers(0, 256, size=(233, 197, 3), dtype=np.uint8)
    png = TMP / "page.png"
    Image.fromarray(rgb).save(png)
    capture, planes, _ = h3intake.ingest_capture(
        png, 1200.0, Fraction(1, 300), Family.CMY8, TMP / "run-png")
    by_key = {(p.level_index, p.plane): p for p in planes}
    check("png sha", capture.capture_id == o_scan._sha256_file(png))
    check("png channels/shape",
          capture.channels == 3 and capture.shape_px == (233, 197))
    check("png native planes byte-identical",
          all(np.array_equal(
              np.asarray(by_key[(capture.levels[-1].index, name)].open()),
              rgb[..., channel])
              for channel, name in enumerate(("r", "g", "b"))))
    check("png plane files land under plane_dir",
          all(p.path.parent == capture.plane_dir for p in planes)
          and capture.plane_dir.name == capture.capture_id[:12])
    # duplicate sha folds
    path = TMP / "grey.tif"
    captures, planes, events = h3intake.ingest_captures(
        (path, path), 2400.0, Fraction(1, 300), Family.K, TMP / "run-dup")
    check("duplicate sha folds to one capture", len(captures) == 1)
    check("duplicate emits a duplicate CaptureOpen",
          len(events) == 2 and events[1].duplicate is True)


# --------------------------------------------------------------------------
# 3. survey kernels + whole survey parity
# --------------------------------------------------------------------------
def _texture(rng: np.random.Generator, cells_y: int, cells_x: int,
             pitch: int, ink: int) -> np.ndarray:
    bits = rng.integers(0, 2, size=(cells_y, cells_x)).astype(np.uint8)
    block = np.kron(bits, np.ones((pitch, pitch), np.uint8))
    return np.where(block > 0, np.uint8(ink), np.uint8(250))


def _page_one(rng: np.random.Generator) -> np.ndarray:
    page = np.full((1024, 1024), np.uint8(252))
    page[200:800, 150:750] = _texture(rng, 150, 150, 4, 30)
    return page


def _page_two(rng: np.random.Generator) -> np.ndarray:
    page = np.full((1024, 1408, 3), np.uint8(251))
    left = _texture(rng, 128, 96, 4, 20)
    right = _texture(rng, 96, 128, 4, 45)
    for channel, ink in enumerate((0.85, 1.0, 0.95)):
        page[160:672, 96:480, channel] = np.clip(
            left.astype(np.float32) * ink, 0, 255).astype(np.uint8)
        page[300:684, 800:1312, channel] = np.clip(
            right.astype(np.float32) * (2.0 - ink), 0, 255).astype(np.uint8)
    return page


def _compare_survey(tag: str, native: np.ndarray, dpi: float,
                    declared: Fraction) -> None:
    raster = o_scan.open_capture(native, dpi)
    want = o_survey.survey_raster(raster, declared_pitch_in=declared)
    planes = ((native,) if native.ndim == 2
              else (native[..., 0], native[..., 1], native[..., 2]))
    view = h3survey.NativeView(dpi=dpi,
                               shape=(native.shape[0], native.shape[1]),
                               planes=planes)
    # tensor score parity, default tiling and a forced multi-tile pass
    px_per_mm = dpi / 25.4
    survey_pitch_px = h3survey.SURVEY_CELL_UM / 1000.0 * px_per_mm
    for tile_cells in (h3survey.TENSOR_TILE_CELLS, 8, 3):
        mine, my_step = h3survey._whole_tensor_score(
            view, survey_pitch_px, tile_cells)
        theirs, their_step = o_tensor._whole_tensor_score(
            raster, survey_pitch_px, tile_cells=tile_cells)
        check(f"{tag} tensor score tile={tile_cells} bit-identical",
              my_step == their_step and np.array_equal(mine, theirs))
    # pitch measurement parity on the largest component's crop
    crop = view.crop_luma(0, min(600, native.shape[0]),
                          0, min(600, native.shape[1]))
    ora_crop = raster.crop_luma(0, min(600, native.shape[0]),
                                0, min(600, native.shape[1]))
    check(f"{tag} crop luma bit-identical", np.array_equal(crop, ora_crop))
    mine_measure = h3survey._measure_cell_pitch(crop)
    try:
        theirs_measure = o_lattice.measure_cell_pitch(
            ora_crop, probes_px=o_survey.PITCH_PROBES_PX)
    except ValueError:
        theirs_measure = None
    if theirs_measure is None:
        check(f"{tag} measure_cell_pitch both decline",
              mine_measure is None)
    else:
        check(f"{tag} measure_cell_pitch pitch/contrast/strong",
              mine_measure is not None
              and mine_measure[0] == theirs_measure.pitch_px
              and mine_measure[1] == theirs_measure.contrast
              and mine_measure[2] == theirs_measure.strong,
              f"{mine_measure} vs {theirs_measure}")
    # whole survey
    raw, voted, pitch_px, score, step = h3survey.survey_view(view, declared)
    check(f"{tag} pitch class {voted}", voted == want.pitch_in,
          f"{voted} != {want.pitch_in}")
    check(f"{tag} pitch px {pitch_px}", pitch_px == want.cell_pitch_px,
          f"{pitch_px} != {want.cell_pitch_px}")
    check(f"{tag} survey step", step == want.diagnostics.survey_step_px)
    check(f"{tag} region count {len(raw)}", len(raw) == len(want.regions),
          f"{len(raw)} != {len(want.regions)}")
    px_per_mm = dpi / 25.4
    mine_sorted = sorted(
        raw,
        key=lambda item: -(h3survey._support_area_px(
            np.asarray(item.support, bool), item.step_px, item.extent_px)
            / (px_per_mm * px_per_mm)))
    for index, (got, ref) in enumerate(zip(mine_sorted, want.regions)):
        area = h3survey._support_area_px(
            np.asarray(got.support, bool), got.step_px,
            got.extent_px) / (px_per_mm * px_per_mm)
        ok = (tuple(got.origin_yx) == tuple(ref.support.origin_yx)
              and got.step_px == ref.support.step_px
              and tuple(got.extent_px) == tuple(ref.support.extent_px)
              and np.array_equal(np.asarray(got.support, bool),
                                 ref.support.cells)
              and area == ref.area_mm2
              and got.score == ref.median_tensor_score)
        check(f"{tag} region {index} identical", ok,
              f"{got.origin_yx}/{got.step_px}/{got.extent_px}/{area} vs "
              f"{ref.support.origin_yx}/{ref.support.step_px}/"
              f"{ref.support.extent_px}/{ref.area_mm2}")
    return None


def test_survey() -> None:
    print("[3] survey parity vs holo2.capture.survey.survey_raster")
    rng = np.random.default_rng(4242)
    page_one = _page_one(rng)
    page_two = _page_two(rng)
    _compare_survey("grid-on-white", page_one, 1200.0, Fraction(1, 300))
    _compare_survey("two-region-rgb", page_two, 1200.0, Fraction(1, 300))
    # a 5-px lattice at 1200 dpi snaps to no candidate: pitch stays None,
    # refinement never runs, regions fall back to coarse survey-step support
    unsnappable = np.full((1024, 1024), np.uint8(252))
    unsnappable[200:800, 150:750] = _texture(rng, 120, 120, 5, 30)
    _compare_survey("no-snappable-pitch", unsnappable, 1200.0,
                    Fraction(1, 300))
    raw, voted, pitch_px, _, step = h3survey.survey_view(
        h3survey.NativeView(1200.0, (1024, 1024), (unsnappable,)),
        Fraction(1, 300))
    check("unsnappable pitch votes None", voted is None and pitch_px is None)
    check("unsnappable admits coarse regions",
          len(raw) >= 1 and all(item.step_px == step for item in raw))
    # the refined pages sit on the fine (printed-pitch) grid, not the
    # 340 um survey grid: the refinement path really ran
    refined, _, _, _, survey_step = h3survey.survey_view(
        h3survey.NativeView(1200.0, (1024, 1024), (page_one,)),
        Fraction(1, 300))
    check("refinement produced a fine-step region",
          len(refined) == 1 and refined[0].step_px == 4 != survey_step)
    blank = np.full((512, 512), np.uint8(255))
    _compare_survey("blank", blank, 1200.0, Fraction(1, 300))
    tiny = np.full((40, 40), np.uint8(200))
    _compare_survey("below-4x-survey-pitch", tiny, 1200.0, Fraction(1, 300))
    # candidate set union (H1(b))
    check("candidate_pitches blind set",
          h3survey.candidate_pitches(None)
          == o_survey.candidate_pitches(None))
    check("candidate_pitches declared member is identity",
          h3survey.candidate_pitches(Fraction(1, 300))
          is h3survey.CANDIDATE_PITCHES_IN)
    check("candidate_pitches adds an unnamed pitch",
          h3survey.candidate_pitches(Fraction(1, 400))
          == o_survey.candidate_pitches(Fraction(1, 400)))
    for pitch_px, dpi in ((4.0, 1200.0), (4.1, 1200.0), (5.0, 1200.0),
                          (8.0, 2400.0), (12.03, 2400.0), (2.0, 1200.0)):
        mine = h3survey._snap_pitch(
            pitch_px, dpi, h3survey.CANDIDATE_PITCHES_IN)
        theirs = o_survey._snap_pitch(
            pitch_px, dpi, o_survey.CANDIDATE_PITCHES_IN)
        check(f"snap {pitch_px}px @{dpi:g} -> {mine}", mine == theirs)


def test_capture_survey() -> None:
    print("[4] survey_capture: data facts, event, declared-vs-voted refusal")
    rng = np.random.default_rng(99)
    page = _page_two(rng)
    path = TMP / "page-two.tif"
    _write_npy_tiff(path, page)
    capture, planes, _ = h3intake.ingest_capture(
        path, 1200.0, Fraction(1, 300), Family.CMY8, TMP / "run-survey")
    survey, events = h3survey.survey_capture(
        capture, planes, Fraction(1, 300))
    raster = o_scan.open_capture(page, 1200.0)
    want = o_survey.survey_raster(raster, declared_pitch_in=Fraction(1, 300))
    check("survey_capture region count",
          len(survey.regions) == len(want.regions))
    check("survey_capture pitch class", survey.pitch_class == want.pitch_in)
    check("survey_capture pitch px", survey.pitch_px == want.cell_pitch_px)
    check("regions sorted by descending area",
          all(survey.regions[i].area_mm2 >= survey.regions[i + 1].area_mm2
              for i in range(len(survey.regions) - 1)))
    for got, ref in zip(survey.regions, want.regions):
        check(f"region {got.region_index} == oracle",
              tuple(got.origin_yx) == tuple(ref.support.origin_yx)
              and got.step_px == ref.support.step_px
              and tuple(got.extent_px) == tuple(ref.support.extent_px)
              and np.array_equal(got.cells, ref.support.cells)
              and got.area_mm2 == ref.area_mm2
              and got.median_tensor_score == ref.median_tensor_score)
        check(f"region {got.region_index} cells read-only",
              not got.cells.flags.writeable)
    check("one SurveyDone event", len(events) == 1
          and type(events[0]).__name__ == "SurveyDone")
    event = events[0]
    check("event marks", len(event.regions) == len(survey.regions)
          and event.n_regions == len(survey.regions))
    check("event pitch class string",
          event.pitch_class == str(survey.pitch_class))
    check("event preview is the tensor grid",
          event.preview is not None
          and event.preview_decim == want.diagnostics.survey_step_px
          and event.preview.shape[0] == page.shape[0] // event.preview_decim)
    # region support crop at native == the historical rasterize_crop
    region = survey.regions[0]
    mask = o_survey.SupportMask(region.origin_yx, region.step_px,
                               region.cells, region.extent_px)
    native_level = capture.levels[-1]
    for box in ((0, 300, 0, 300), (100, 700, 90, 640), (900, 1000, 1300,
                                                        1400)):
        got = h3intake.region_support_crop(region, native_level, *box)
        check(f"region_support_crop native {box}",
              np.array_equal(got, mask.rasterize_crop(*box)))
    coarse = capture.levels[0]
    from holo2.capture.footing_raster import FootingFrame
    frame = FootingFrame.of(
        coarse.ppc, o_scale.native_pixels_per_cell(1200.0, Fraction(1, 300)),
        capture.shape_px)
    for box in ((0, 150, 0, 150), (50, 350, 40, 320)):
        got = h3intake.region_support_crop(region, coarse, *box)
        check(f"region_support_crop coarse {box}",
              np.array_equal(got, frame.support_crop(mask, *box)))
    # e033 refusal
    try:
        h3survey.survey_capture(capture, planes, Fraction(1, 200))
        check("declared-vs-voted pitch refusal", False, "no refusal")
    except ValueError as exc:
        check("declared-vs-voted pitch refusal",
              "1/300" in str(exc) and "1/200" in str(exc), str(exc))


CORPUS = Path("scratch/in")
REAL = (
    ("xerox-canon-c2-bw.tiff", 4800.0, Fraction(1, 300),
     (24000, 32192, 16000, 24192)),
    ("xerox-canon-c2-cmy8.tiff", 4800.0, Fraction(1, 300),
     (24000, 28096, 16000, 20096)),
    ("xerox-canon-c3-cmy7-2400dpi.tiff", 2400.0, Fraction(1, 200),
     (12000, 16096, 8000, 12096)),
)


def test_real_captures() -> None:
    print("[5] real-capture reads (read-only corpus)")
    for name, dpi, pitch, box in REAL:
        path = CORPUS / name
        if not path.is_file():
            print(f"  skip {name} (absent)")
            continue
        native = h3intake.load_native(path)
        check(f"{name} memmapped u8",
              isinstance(native, np.memmap) and native.dtype == np.uint8)
        check(f"{name} ladder",
              h3intake.build_levels(dpi, pitch, native.shape[:2])[-1].scale
              == 1)
        y0, y1, x0, x1 = box
        crop = np.ascontiguousarray(native[y0:y1, x0:x1])
        del native
        _compare_survey(f"real:{name}", crop, dpi, pitch)


def main() -> int:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    try:
        test_ladder()
        test_decimation()
        test_survey()
        test_capture_survey()
        test_real_captures()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    if FAILURES:
        for line in FAILURES:
            print(f"  FAILED: {line}")
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
