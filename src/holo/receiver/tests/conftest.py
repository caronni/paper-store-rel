from __future__ import annotations

from collections.abc import Callable, Iterator
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo.receiver.format import identity
from holo.receiver.tests import (_h3_fixture_geometry, _h3_sims,
                                _h3_sims_cmy, _h3_sims_p_axis, _h3_support)
from holo.receiver.tests._h3_fixture_build import (
    _WORK_LOCK,
    DecodeRecord,
    _decode_group,
    _decode_once,
    _materialise,
    _sim_gate,
)
# An imported fixture function is a REGISTERED fixture, which is how the
# page-field lane's seven fixtures live in their own module while every
# test still asks for them by name (W6; `pytest_plugins` is refused in a
# non-root conftest).  The two hold-out row sets used to be imported
# here as well, for the yield fixtures that shared them; those retired
# 2026-09-20 (docs/WIDENED-MATRIX-RETIREMENT-2026-09-20.md) and the sets
# are read where they are declared.
from holo.receiver.tests._h3_fixtures_field import (
    decode_color_confetti,
    decode_color_shifted,
    decode_color_shifted_rot2,
    decode_color_shifted_unfielded,
    sim_color_confetti,
    sim_color_shifted,
    sim_color_shifted_rot2,
)

#: The page-field fixtures, bound here so pytest registers them: a
#: fixture function imported into a conftest IS a fixture of that
#: conftest, and this tuple is what says the binding is deliberate
#: rather than a leftover import.
FIELD_FIXTURES = (
    sim_color_shifted, sim_color_shifted_rot2, sim_color_confetti,
    decode_color_shifted, decode_color_shifted_unfielded,
    decode_color_shifted_rot2, decode_color_confetti,
)

NULL_RASTER_SEED = 20260829
NULL_RASTER_PAPER = 245.0
NULL_RASTER_NOISE_SD = 3.0

# the keep box is (top, bottom, left, right); its left edge is the one
# live dial and moved for the b8471fc re-key — record in test_h3_degraded_sim
DEGRADED_SEED = 20260829
DEGRADED_NOISE_SD = 25.0
DEGRADED_KEEP_BOX = (0.35, 0.65, 0.3625, 0.65)

# The local-context capture: one window of the K sim reads through a
# different channel from the other eight.  The patch is the raster of
# window (0, 0) -- cells [0, WINDOW_CELLS) on both axes -- given a
# directional smear (the process-direction ISI the engines actually
# have) and its own noise, while the rest of the page keeps the frozen
# render.  A context detector fitted over the whole region is then
# fitted on a channel that holds for eight ninths of it and not for the
# ninth; the row under test fits the ninth on its own.  The noise sd is a
# searched point (49 -> 35 for the b8471fc re-key); ladder and reasoning
# in test_h3_plugins_local_ctx.
LOCAL_PATCH_SEED = 20260830
LOCAL_PATCH_CELLS = 200          # = geometry.WINDOW_CELLS
LOCAL_PATCH_BORDER_PX = 192      # K_BORDER_DOTS 96 x UPSAMPLE 2
LOCAL_PATCH_CELL_PX = 6          # K_CELL_DOTS 3 x UPSAMPLE 2
LOCAL_PATCH_SMEAR_PX = 5.0
LOCAL_PATCH_NOISE_SD = 35.0


@pytest.fixture(scope="session", autouse=True)
def memoised_site_geometry_for_the_lane() -> Iterator[None]:
    # ``identity.build_site_geometry`` is a pure function of the row that
    # every fixture engine paid again through ``store.__init__``: measured
    # 2026-09-05, 258 calls = 27.2 s of a 49.8 s serial fast lane.  The
    # memo and its one constraint live in _h3_fixture_geometry.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(identity, "build_site_geometry",
                      _h3_fixture_geometry.memoised_site_geometry)
        yield


@pytest.fixture(scope="session")
def sim_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("h3-sims")


@pytest.fixture(scope="session")
def sim_k(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the K sim capture")
    with _WORK_LOCK:
        outdir = _materialise("k", _h3_sims.make_k, _h3_sims.EXPECTED_K,
                              sim_root)
    return _h3_sims.capture_k(outdir)


@pytest.fixture(scope="session")
def sim_color(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the colour sim capture")
    with _WORK_LOCK:
        outdir = _materialise("color", _h3_sims.make_color,
                              _h3_sims.EXPECTED_COLOR, sim_root)
    return _h3_sims.capture_color(outdir)


def _rot_factory(base: _h3_sims.SimCapture,
                 root: Path) -> Callable[[int], _h3_sims.SimCapture]:
    built: dict[int, _h3_sims.SimCapture] = {}

    def rotated(rot_k: int) -> _h3_sims.SimCapture:
        if rot_k == 0:
            return base
        if rot_k not in built:
            with _WORK_LOCK:
                built[rot_k] = _h3_sims.rotated_capture(base, rot_k, root)
        return built[rot_k]

    return rotated


@pytest.fixture(scope="session")
def sim_k_rot(sim_k: _h3_sims.SimCapture,
              sim_root: Path) -> Callable[[int], _h3_sims.SimCapture]:
    return _rot_factory(sim_k, sim_root / "rot")


@pytest.fixture(scope="session")
def sim_color_rot(sim_color: _h3_sims.SimCapture,
                  sim_root: Path) -> Callable[[int], _h3_sims.SimCapture]:
    return _rot_factory(sim_color, sim_root / "rot")


@pytest.fixture(scope="session")
def sim_k_null(sim_k: _h3_sims.SimCapture,
               sim_root: Path) -> _h3_sims.SimCapture:
    import tifffile

    target = sim_root / "null" / "sim-k-null-1200dpi.tiff"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shape = tifffile.imread(sim_k.tiff).shape
        rng = np.random.default_rng(NULL_RASTER_SEED)
        noise = rng.normal(0.0, NULL_RASTER_NOISE_SD, size=shape)
        paper = np.clip(NULL_RASTER_PAPER + noise, 0, 255).astype(np.uint8)
        tifffile.imwrite(target, paper)
    return _h3_sims.SimCapture(
        name="k-null", format_ref=sim_k.format_ref, dpi=sim_k.dpi, rot_k=0,
        tiff=target, tiff_sha256=_h3_sims.sha256_file(target),
        payload=sim_k.payload, payload_sha256=sim_k.payload_sha256,
        payload_bytes=sim_k.payload_bytes, emit_dir=None)


def _degraded_raster(image: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(DEGRADED_SEED)
    noisy = image.astype(np.float32) + rng.normal(
        0.0, DEGRADED_NOISE_SD, size=image.shape)
    height, width = image.shape
    top, bottom, left, right = DEGRADED_KEEP_BOX
    kept = np.full(image.shape, NULL_RASTER_PAPER, np.float32)
    rows = slice(int(height * top), int(height * bottom))
    columns = slice(int(width * left), int(width * right))
    kept[rows, columns] = noisy[rows, columns]
    return np.round(np.clip(kept, 0, 255)).astype(np.uint8)


def _local_patch_raster(image: np.ndarray) -> np.ndarray:
    from scipy import ndimage

    stop = (LOCAL_PATCH_BORDER_PX
            + LOCAL_PATCH_CELLS * LOCAL_PATCH_CELL_PX)
    rows = slice(LOCAL_PATCH_BORDER_PX, stop)
    columns = slice(LOCAL_PATCH_BORDER_PX, stop)
    patch = image[rows, columns].astype(np.float32)
    smeared = ndimage.gaussian_filter1d(patch, LOCAL_PATCH_SMEAR_PX, axis=1,
                                        mode="nearest")
    rng = np.random.default_rng(LOCAL_PATCH_SEED)
    noisy = smeared + rng.normal(0.0, LOCAL_PATCH_NOISE_SD, patch.shape)
    out = image.astype(np.float32).copy()
    out[rows, columns] = noisy
    return np.round(np.clip(out, 0, 255)).astype(np.uint8)


@pytest.fixture(scope="session")
def sim_k_local_patch(sim_k: _h3_sims.SimCapture,
                      sim_root: Path) -> _h3_sims.SimCapture:
    import tifffile

    target = sim_root / "local-patch" / "sim-k-local-patch-1200dpi.tiff"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(target,
                         _local_patch_raster(tifffile.imread(sim_k.tiff)))
    return _h3_sims.SimCapture(
        name="k-local-patch", format_ref=sim_k.format_ref, dpi=sim_k.dpi,
        rot_k=0, tiff=target, tiff_sha256=_h3_sims.sha256_file(target),
        payload=sim_k.payload, payload_sha256=sim_k.payload_sha256,
        payload_bytes=sim_k.payload_bytes, emit_dir=None)


@pytest.fixture(scope="session")
def decode_k_local_patch_w1(sim_k_local_patch: _h3_sims.SimCapture,
                            decode_root: Path) -> DecodeRecord:
    return _decode_once("k-local-patch-w1", sim_k_local_patch, decode_root,
                        workers=1, extra_argv=("--complete", "--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_k_local_patch_off_w1(sim_k_local_patch: _h3_sims.SimCapture,
                                decode_root: Path) -> DecodeRecord:
    return _decode_once("k-local-patch-off-w1", sim_k_local_patch,
                        decode_root, workers=1,
                        extra_argv=("--complete", "--max-pages", "1"),
                        drop_rows=("tiles.local",))


@pytest.fixture(scope="session")
def decode_k_local_patch_w8(sim_k_local_patch: _h3_sims.SimCapture,
                            decode_root: Path) -> DecodeRecord:
    # keeps its engine (so it is never cached): the finished live store
    # is what the contradiction alarms and the replay-transience proof
    # read, and at eight workers it is 4 s where the one-worker pair --
    # which carries the on/off existence proof -- is 36 s per arm
    return _decode_once("k-local-patch-w8", sim_k_local_patch, decode_root,
                        workers=8,
                        extra_argv=("--complete", "--max-pages", "1"),
                        keep_engine=True)
@pytest.fixture(scope="session")
def sim_k_degraded(sim_k: _h3_sims.SimCapture,
                   sim_root: Path) -> _h3_sims.SimCapture:
    import tifffile

    target = sim_root / "degraded" / "sim-k-degraded-1200dpi.tiff"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(target,
                         _degraded_raster(tifffile.imread(sim_k.tiff)))
    return _h3_sims.SimCapture(
        name="k-degraded", format_ref=sim_k.format_ref, dpi=sim_k.dpi,
        rot_k=0, tiff=target, tiff_sha256=_h3_sims.sha256_file(target),
        payload=sim_k.payload, payload_sha256=sim_k.payload_sha256,
        payload_bytes=sim_k.payload_bytes, emit_dir=None)


# The RIVAL-PITCH capture: the K sim page with a second lattice beside
# it, printed at a different CANDIDATE pitch, so the survey's plurality
# ties one vote each and the capture votes no printed pitch at all.
# Stimulus ladder and the before/after numbers in
# test_h3_survey_pitch_fallback.py.
RIVAL_PITCH_IN = Fraction(1, 150)
RIVAL_PITCH_CELLS = 24
RIVAL_PITCH_GAP_PX = 96
RIVAL_PITCH_SEED = 20260904


def _rival_pitch_raster(image: np.ndarray, dpi: float) -> np.ndarray:
    rng = np.random.default_rng(RIVAL_PITCH_SEED)
    cell_px = int(RIVAL_PITCH_IN * dpi)
    bits = rng.random((RIVAL_PITCH_CELLS, RIVAL_PITCH_CELLS)) < 0.5
    patch = np.kron(
        np.where(bits, _h3_sims.K_INK_LEVEL,
                 _h3_sims.K_PAPER_LEVEL).astype(np.uint8),
        np.ones((cell_px, cell_px), np.uint8))
    out = np.full((image.shape[0],
                   image.shape[1] + 2 * RIVAL_PITCH_GAP_PX + patch.shape[1]),
                  _h3_sims.K_PAPER_LEVEL, np.uint8)
    out[:, :image.shape[1]] = image
    y0 = (image.shape[0] - patch.shape[0]) // 2
    x0 = image.shape[1] + RIVAL_PITCH_GAP_PX
    out[y0:y0 + patch.shape[0], x0:x0 + patch.shape[1]] = patch
    return out


@pytest.fixture(scope="session")
def sim_k_rival_pitch(sim_k: _h3_sims.SimCapture,
                      sim_root: Path) -> _h3_sims.SimCapture:
    import tifffile

    target = sim_root / "rival-pitch" / "sim-k-rival-pitch-1200dpi.tiff"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(target, _rival_pitch_raster(
            tifffile.imread(sim_k.tiff), sim_k.dpi))
    return _h3_sims.SimCapture(
        name="k-rival-pitch", format_ref=sim_k.format_ref, dpi=sim_k.dpi,
        rot_k=0, tiff=target, tiff_sha256=_h3_sims.sha256_file(target),
        payload=sim_k.payload, payload_sha256=sim_k.payload_sha256,
        payload_bytes=sim_k.payload_bytes, emit_dir=None)


@pytest.fixture(scope="session")
def decode_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("h3-decodes")


@pytest.fixture(scope="session")
def decode_k_w1(sim_k: _h3_sims.SimCapture,
                decode_root: Path) -> DecodeRecord:
    return _decode_once("k-w1", sim_k, decode_root, workers=1)


@pytest.fixture(scope="session")
def decode_k_w8(sim_k: _h3_sims.SimCapture,
                decode_root: Path) -> DecodeRecord:
    return _decode_once("k-w8", sim_k, decode_root, workers=8)


@pytest.fixture(scope="session")
def decode_k_rot(sim_k_rot: Callable[[int], _h3_sims.SimCapture],
                 decode_root: Path) -> Callable[[int], DecodeRecord]:
    done: dict[int, DecodeRecord] = {}

    def decode(rot_k: int) -> DecodeRecord:
        if rot_k not in done:
            done[rot_k] = _decode_once(
                f"k-rot{rot_k}", sim_k_rot(rot_k), decode_root, workers=8,
                extra_argv=("--max-pages", "1"))
        return done[rot_k]

    return decode


@pytest.fixture(scope="session")
def decode_color_w8(sim_color: _h3_sims.SimCapture,
                    decode_root: Path) -> DecodeRecord:
    return _decode_once("color-w8", sim_color, decode_root, workers=8,
                        extra_argv=("--max-pages", "1"))


@pytest.fixture(scope="session")
def sim_color_groups(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the column-group colour sim capture")
    with _WORK_LOCK:
        outdir = _materialise("color-groups", _h3_sims.make_color_groups,
                              _h3_sims.EXPECTED_GROUPS, sim_root)
    return _h3_sims.capture_color_groups(outdir)


@pytest.fixture(scope="session")
def sim_color_groups_dead_y(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the column-group dead-Y colour sim capture")
    with _WORK_LOCK:
        outdir = _materialise("color-groups", _h3_sims.make_color_groups,
                              _h3_sims.EXPECTED_GROUPS, sim_root)
    return _h3_sims.capture_color_groups(outdir, dead_y=True)


@pytest.fixture(scope="session")
def sim_p_axis(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the p300 furniture-density colour sim capture")
    with _WORK_LOCK:
        outdir = _materialise("p-axis", _h3_sims_p_axis.make_p_axis,
                              _h3_sims_p_axis.EXPECTED_P_AXIS, sim_root)
    return _h3_sims_p_axis.capture_p_axis(outdir)


@pytest.fixture(scope="session")
def decode_p_axis_w8(sim_p_axis: _h3_sims.SimCapture,
                     decode_root: Path) -> DecodeRecord:
    return _decode_once("p-axis-w8", sim_p_axis, decode_root, workers=8,
                        extra_argv=("--max-pages", "1"))


@pytest.fixture(scope="session")
def sim_p_axis_k(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the p300 furniture-density K sim capture")
    with _WORK_LOCK:
        outdir = _materialise("p-axis-k", _h3_sims_p_axis.make_p_axis_k,
                              _h3_sims_p_axis.EXPECTED_P_AXIS_K, sim_root)
    return _h3_sims_p_axis.capture_p_axis_k(outdir)


@pytest.fixture(scope="session")
def decode_p_axis_k_w8(sim_p_axis_k: _h3_sims.SimCapture,
                       decode_root: Path) -> DecodeRecord:
    return _decode_once("p-axis-k-w8", sim_p_axis_k, decode_root, workers=8,
                        extra_argv=("--max-pages", "1"))


@pytest.fixture(scope="session")
def sim_cmy(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the c3 cmy sim capture")
    with _WORK_LOCK:
        outdir = _materialise("cmy", _h3_sims_cmy.make_cmy,
                              _h3_sims_cmy.EXPECTED_CMY, sim_root)
    return _h3_sims_cmy.capture_cmy(outdir)


# Placement and addressing alone: the colour row dropped, nothing
# certifies and placement runs to exhaustion, so every tile's address
# coverage is on the record -- the whole decode below closes first, with
# tiles still unaddressed.
@pytest.fixture(scope="session")
def decode_cmy_place_w8(sim_cmy: _h3_sims.SimCapture,
                        decode_root: Path) -> DecodeRecord:
    return _decode_once("cmy-place-w8", sim_cmy, decode_root, workers=8,
                        extra_argv=("--max-pages", "1"),
                        drop_rows=("color",))


# The whole cmy decode, the first close (CMY-RECEIVER-PLAN A4): the
# colour sim's argv, so a cmy page is decoded as a cmy8 one is.
@pytest.fixture(scope="session")
def decode_cmy_w8(sim_cmy: _h3_sims.SimCapture,
                  decode_root: Path) -> DecodeRecord:
    return _decode_once("cmy-w8", sim_cmy, decode_root, workers=8,
                        extra_argv=("--max-pages", "1"))


@pytest.fixture(scope="session")
def sim_cmy_offset(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the offset c3 cmy sim capture")
    with _WORK_LOCK:
        outdir = _materialise("cmy-offset", _h3_sims_cmy.make_cmy_offset,
                              _h3_sims_cmy.EXPECTED_CMY_OFFSET, sim_root)
    return _h3_sims_cmy.capture_cmy_offset(outdir)


# The offset page decoded as the in-register one is (CMY-RECEIVER-PLAN
# A5): M and Y a dot out of register, read through the page field.
@pytest.fixture(scope="session")
def decode_cmy_offset_w8(sim_cmy_offset: _h3_sims.SimCapture,
                         decode_root: Path) -> DecodeRecord:
    # --complete since 2026-10-12: at eight workers the close could land
    # before the page field solved (the A5 ledger: the field solved in
    # some runs and not others), and two tests read the field --
    # draining every row makes the record deterministic in what it holds.
    return _decode_once("cmy-offset-w8", sim_cmy_offset, decode_root,
                        workers=8,
                        extra_argv=("--complete", "--max-pages", "1"))


@pytest.fixture(scope="session")
def sim_cmy_faint(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the faint c3 cmy sim capture")
    with _WORK_LOCK:
        outdir = _materialise("cmy-faint", _h3_sims_cmy.make_cmy_faint,
                              _h3_sims_cmy.EXPECTED_CMY_FAINT, sim_root)
    return _h3_sims_cmy.capture_cmy_faint(outdir)


# The cmy residue decode (CMY-RECEIVER-PLAN A7): the faint page with every
# row on, run to the end of its frontier (`--complete`), as the K
# local-patch decodes are.
@pytest.fixture(scope="session")
def decode_cmy_faint_w8(sim_cmy_faint: _h3_sims.SimCapture,
                        decode_root: Path) -> DecodeRecord:
    return _decode_once("cmy-faint-w8", sim_cmy_faint, decode_root,
                        workers=8,
                        extra_argv=("--complete", "--max-pages", "1"))


@pytest.fixture(scope="session")
def sim_cmy_c2(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the c2 cmy sim capture at 2400 dpi")
    with _WORK_LOCK:
        outdir = _materialise("cmy-c2", _h3_sims_cmy.make_cmy_c2,
                              _h3_sims_cmy.EXPECTED_CMY_C2, sim_root)
    return _h3_sims_cmy.capture_cmy_c2(outdir)


@pytest.fixture(scope="session")
def sim_cmy_c2_dead(sim_root: Path) -> Callable[[str], _h3_sims.SimCapture]:
    _sim_gate("the dead-plane c2 cmy sim captures")
    with _WORK_LOCK:
        outdir = _materialise("cmy-c2", _h3_sims_cmy.make_cmy_c2,
                              _h3_sims_cmy.EXPECTED_CMY_C2, sim_root)
    return lambda toner: _h3_sims_cmy.capture_cmy_c2_dead(outdir, toner)


# The c2 page (CMY-RECEIVER-PLAN A9) and G8's dead-toner twins, each
# decoded as the c3 cmy pages are: eight workers, one page.
@pytest.fixture(scope="session")
def decode_cmy_c2_w8(sim_cmy_c2: _h3_sims.SimCapture,
                     decode_root: Path) -> DecodeRecord:
    return _decode_once("cmy-c2-w8", sim_cmy_c2, decode_root, workers=8,
                        extra_argv=("--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_cmy_c2_dead(sim_cmy_c2_dead: Callable[[str], _h3_sims.SimCapture],
                       decode_root: Path) -> Callable[[str], DecodeRecord]:
    done: dict[str, DecodeRecord] = {}

    def decode(toner: str) -> DecodeRecord:
        if toner not in done:
            done[toner] = _decode_once(
                f"cmy-c2-dead-{toner.lower()}-w8", sim_cmy_c2_dead(toner),
                decode_root, workers=8, extra_argv=("--max-pages", "1"))
        return done[toner]

    return decode


@pytest.fixture(scope="session")
def sim_cmy_c2_crop(sim_root: Path) -> Callable[..., _h3_sims.SimCapture]:
    _sim_gate("the c2 cmy fragments")
    with _WORK_LOCK:
        outdir = _materialise("cmy-c2-crops", _h3_sims_cmy.make_cmy_c2_crops,
                              _h3_sims_cmy.EXPECTED_CMY_C2_CROPS, sim_root)
    return lambda shape, plant, drift: _h3_sims_cmy.capture_cmy_c2_crop(
        outdir, shape, plant, drift)


# G12's cold start: a 2x3-tile scrap, nothing certified, decoded at ONE
# worker so the field it solves and the tiles it certifies are one
# deterministic run; no close is possible below metadata trust, so the
# frontier drains whatever the argv.
@pytest.fixture(scope="session")
def decode_cmy_c2_crop(sim_cmy_c2_crop: Callable[..., _h3_sims.SimCapture],
                       decode_root: Path) -> Callable[..., DecodeRecord]:
    done: dict[tuple[tuple[int, int], str, str], DecodeRecord] = {}

    def decode(shape: tuple[int, int], plant: str,
               drift: str) -> DecodeRecord:
        key = (shape, plant, drift)
        if key not in done:
            capture = sim_cmy_c2_crop(*key)
            done[key] = _decode_once(f"{capture.name}-w1", capture,
                                     decode_root, workers=1,
                                     extra_argv=("--max-pages", "1"))
        return done[key]

    return decode


@pytest.fixture(scope="session")
def sim_color_groups_pages(sim_root: Path) -> tuple[_h3_sims.SimCapture, ...]:
    _sim_gate("the three-page column-group colour sim")
    with _WORK_LOCK:
        outdir = _materialise("color-groups-pages",
                              _h3_sims.make_color_groups_pages,
                              _h3_sims.EXPECTED_PAGES, sim_root)
    return _h3_sims.capture_color_groups_pages(outdir)


@pytest.fixture(scope="session")
def decode_color_groups_pages_w8(sim_color_groups_pages, decode_root: Path
                                 ) -> DecodeRecord:
    return _decode_group("color-groups-pages-w8", sim_color_groups_pages,
                         decode_root, workers=8,
                         extra_argv=("--max-pages", "3"))


@pytest.fixture(scope="session")
def decode_color_groups_w8(sim_color_groups: _h3_sims.SimCapture,
                           decode_root: Path) -> DecodeRecord:
    return _decode_once("color-groups-w8", sim_color_groups, decode_root,
                        workers=8, extra_argv=("--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_color_groups_dead_y_w8(
        sim_color_groups_dead_y: _h3_sims.SimCapture,
        decode_root: Path) -> DecodeRecord:
    return _decode_once("color-groups-dead-y-w8", sim_color_groups_dead_y,
                        decode_root, workers=8,
                        extra_argv=("--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_color_rot1(sim_color_rot: Callable[[int], _h3_sims.SimCapture],
                      decode_root: Path) -> DecodeRecord:
    return _decode_once("color-rot1", sim_color_rot(1), decode_root,
                        workers=8, extra_argv=("--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_k_no_close(sim_k: _h3_sims.SimCapture,
                      decode_root: Path) -> DecodeRecord:
    return _decode_once("k-no-close", sim_k, decode_root, workers=8,
                        extra_argv=("--no-close", "--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_k_complete(sim_k: _h3_sims.SimCapture,
                      decode_root: Path) -> DecodeRecord:
    return _decode_once("k-complete", sim_k, decode_root, workers=8,
                        extra_argv=("--complete", "--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_k_diag_broken(sim_k: _h3_sims.SimCapture,
                         decode_root: Path) -> DecodeRecord:
    """The K page decoded with the diag fold raising — the C-11 witness.

    Bounded to one page 2026-09-05 (measured 12.8 s -> ~3 s, every
    assertion in test_h3_e2e_sims intact): the run still verifies, which
    is the whole law, and the search for the planned-but-absent page 1
    that the unbounded shape pays for stays exercised by decode_k_w1/w8.
    """
    from unittest import mock

    from holo.receiver.diag import model

    def broken_fold(*args: object, **kwargs: object) -> object:
        raise RuntimeError("diag deliberately broken for C-11")

    # `cache_tag` NAMES THE PATCH: the decode cache keys on the source
    # tree and cannot see a fold this fixture replaced, so a change to
    # `broken_fold` is a change to the tag.
    with mock.patch.object(model, "fold", broken_fold):
        return _decode_once("k-diag-broken", sim_k, decode_root, workers=8,
                            extra_argv=("--max-pages", "1"),
                            cache_tag="diag-model-fold-raises")


@pytest.fixture(scope="session")
def decode_k_null(sim_k_null: _h3_sims.SimCapture,
                  decode_root: Path) -> DecodeRecord:
    return _decode_once("k-null", sim_k_null, decode_root, workers=8,
                        extra_argv=("--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_k_degraded_w1(sim_k_degraded: _h3_sims.SimCapture,
                         decode_root: Path) -> DecodeRecord:
    return _decode_once("k-degraded-w1", sim_k_degraded, decode_root,
                        workers=1,
                        extra_argv=("--complete", "--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_k_rival_pitch_w1(sim_k_rival_pitch: _h3_sims.SimCapture,
                            decode_root: Path) -> DecodeRecord:
    return _decode_once("k-rival-pitch-w1", sim_k_rival_pitch, decode_root,
                        workers=1, extra_argv=("--max-pages", "1"))


@pytest.fixture(scope="session")
def sim_k_mixed(sim_k: _h3_sims.SimCapture, sim_root: Path,
                ) -> tuple[_h3_sims.SimCapture, _h3_sims.SimCapture]:
    with _WORK_LOCK:
        outdir = _materialise(
            "k-mixed",
            lambda staging: _h3_sims.make_k_mixed(sim_k.tiff, staging),
            _h3_sims.EXPECTED_MIXED, sim_root)
    return _h3_sims.capture_k_mixed(outdir, sim_k)


@pytest.fixture(scope="session")
def sim_k_pages_0_2(sim_root: Path) -> tuple[_h3_sims.SimCapture, ...]:
    _sim_gate("the 3-page word-open sim")
    with _WORK_LOCK:
        outdir = _materialise("k-pages-0-2", _h3_sims.make_k_pages,
                              _h3_sims.EXPECTED_PAGE_DOMAIN, sim_root)
    return _h3_sims.capture_k_pages(outdir)


@pytest.fixture(scope="session")
def decode_k_pages_0_2(sim_k_pages_0_2, decode_root: Path) -> DecodeRecord:
    # eight workers, measured 2026-09-05: the serial arm cost 33.9 s and
    # this one 6.9 s for the same certificates and the same three pins,
    # none of which is order-dependent.  `--complete` stays: the
    # exhaustive harvest is what makes page 2 open structurally rather
    # than because the close happened to need it.
    return _decode_group("k-pages-0-2", sim_k_pages_0_2, decode_root,
                         workers=8,
                         extra_argv=("--complete", *_h3_sims.PAGE_DOMAIN_BOUND),
                         keep_engine=True)


# `decode_color_w1_fields` retired 2026-09-20 with the field-yield
# module, its only consumer: it decoded THIS sim under a second label
# with the argv `decode_color_w1` below already uses, and the clean
# colour page is measured there.
@pytest.fixture(scope="session")
def decode_color_w1(sim_color: _h3_sims.SimCapture,
                    decode_root: Path) -> DecodeRecord:
    _h3_support.skip_unless_oracle_sweeps("the serial clean colour decode")
    return _decode_once("color-w1", sim_color, decode_root, workers=1,
                        extra_argv=("--complete", "--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_k_mixed_w1(sim_k_mixed, decode_root: Path) -> DecodeRecord:
    return _decode_group("k-mixed-w1", sim_k_mixed, decode_root,
                         workers=1, extra_argv=("--complete", "--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_k_mixed_w8(sim_k_mixed, decode_root: Path) -> DecodeRecord:
    # the widened matrix, not the ordinary sim lane (2026-09-05): worker
    # invariance of a recovered payload is pinned on three other decodes,
    # and what this one uniquely covers — cross-capture union
    # commutativity — is worth a lane rather than 11 s of every slow run.
    _h3_support.skip_unless_oracle_sweeps("the mixed-capture pooled decode")
    return _decode_group("k-mixed-w8", sim_k_mixed, decode_root, workers=8)
