from __future__ import annotations

import contextlib
import hashlib
import io
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

import numpy as np
import pytest

from holo3 import cli, data, engine
from holo3.tests import _h3_sims, _h3_support

V1_WORKERS_ENV = "HOLO_RECEIVE_WORKERS"

_WORK_LOCK = threading.Lock()

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

# The colour local-head capture: one window of the colour sim reads
# through its own PLANE GEOMETRY.  The patch is the raster of window
# (0, 0) — cells [0, 200)^2 — where the C-bearing channel is sampled
# 5 px (0.83 cell) off in x and the window carries its own noise.  The
# mechanism is the measured one: e033 found a real per-plane
# x-registration sinusoid on the AltaLink, and `color_region` fits ONE
# residual model per plane over the whole page as a function of page-y,
# so a jump confined to a single window is averaged away there and is
# exactly representable by a fit over that window alone.
COLOR_PATCH_SEED = 20260830
COLOR_PATCH_CELLS = 200          # = geometry.WINDOW_CELLS
COLOR_PATCH_BORDER_PX = 120      # COLOR_BORDER_DOTS 60 x UPSAMPLE 2
COLOR_PATCH_CELL_PX = 6          # K_CELL_DOTS 3 x UPSAMPLE 2
COLOR_PATCH_CHANNEL = 0          # R — the channel cyan absorbs
COLOR_PATCH_SHIFT_PX = 5
COLOR_PATCH_NOISE_SD = 60.0


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config._holo3_started_at = time.monotonic()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    started = getattr(session.config, "_holo3_started_at", None)
    if started is None:
        return
    message = _h3_support.wall_tripwire_message(
        time.monotonic() - started, _h3_support.lane_name())
    if message is None:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(f"holo3 wall tripwire: {message}", red=True)
    session.exitstatus = 1


@pytest.fixture(scope="session", autouse=True)
def v1_serial_workers() -> object:
    previous = os.environ.get(V1_WORKERS_ENV)
    os.environ[V1_WORKERS_ENV] = "1"
    try:
        yield "1"
    finally:
        if previous is None:
            os.environ.pop(V1_WORKERS_ENV, None)
        else:
            os.environ[V1_WORKERS_ENV] = previous


@pytest.fixture(scope="session")
def session_elapsed_s(request: pytest.FixtureRequest) -> Callable[[], float]:
    started = getattr(request.config, "_holo3_started_at", None)

    def elapsed() -> float:
        if started is None:
            return 0.0
        return time.monotonic() - started

    return elapsed


def _cache_key() -> str:
    digest = hashlib.sha256()
    digest.update(_h3_sims.SOURCE_DIGEST.encode())
    digest.update(str(_h3_sims.RENDER_CACHE_VERSION).encode())
    digest.update(_h3_sims.K_FORMAT_REF.encode())
    digest.update(_h3_sims.COLOR_FORMAT_REF.encode())
    digest.update(_h3_sims.K_PAYLOAD_TAG)
    digest.update(_h3_sims.COLOR_PAYLOAD_TAG)
    digest.update(_h3_sims.HARD_FORMAT_REF.encode())
    digest.update(_h3_sims.HARD_PAYLOAD_TAG)
    digest.update(_h3_sims.GROUPS_FORMAT_REF.encode())
    digest.update(_h3_sims.GROUPS_PAYLOAD_TAG)
    digest.update(_h3_sims.PAGES_PAYLOAD_TAG)
    return digest.hexdigest()[:16]


def _cache_root() -> Path | None:
    declared = os.environ.get(_h3_support.FIXTURE_CACHE_ENV)
    if declared is not None and declared.strip() == "":
        return None
    base = (Path(declared) if declared
            else Path(tempfile.gettempdir()) / "holo3-fixture-cache")
    return base / _cache_key()


def _raise_on_mismatch(name: str, outdir: Path,
                       expected: dict[str, str]) -> None:
    problem = _h3_sims.verify(outdir, expected)
    if problem is None:
        return
    raise RuntimeError(
        f"FIXTURE FAILURE: freshly generated {name} sim does not match its "
        f"frozen artefacts ({problem}). This is src/holo generator drift or "
        f"a numeric-stack change in the render path — never a holo3 "
        f"receiver regression. Bump _h3_sims.RENDER_CACHE_VERSION only "
        f"after the drift itself is understood and ruled on.")


def _materialise(name: str, builder: Callable[[Path], object],
                 expected: dict[str, str], fallback_root: Path) -> Path:
    root = _cache_root()
    if root is None:
        target = fallback_root / name
        if _h3_sims.verify(target, expected) is not None:
            builder(target)
            _raise_on_mismatch(name, target, expected)
        return target
    target = root / name
    if _h3_sims.verify(target, expected) is None:
        return target
    staging = root / f".{name}.{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    builder(staging)
    _raise_on_mismatch(name, staging, expected)
    try:
        os.replace(staging, target)
    except OSError:
        if _h3_sims.verify(target, expected) is None:
            shutil.rmtree(staging, ignore_errors=True)
        else:
            shutil.rmtree(target, ignore_errors=True)
            os.replace(staging, target)
    return target


def _sim_gate(what: str) -> None:
    _h3_support.skip_unless_slow_lane(what)
    reason = _h3_sims.producer_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)


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
                        workers=1, extra_argv=("--complete", "--max-pages", "1"),
                        keep_engine=True)


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
    return _decode_once("k-local-patch-w8", sim_k_local_patch, decode_root,
                        workers=8,
                        extra_argv=("--complete", "--max-pages", "1"))


def _color_patch_raster(image: np.ndarray) -> np.ndarray:
    stop = (COLOR_PATCH_BORDER_PX
            + COLOR_PATCH_CELLS * COLOR_PATCH_CELL_PX)
    rows = slice(COLOR_PATCH_BORDER_PX, stop)
    columns = slice(COLOR_PATCH_BORDER_PX, stop)
    shifted = slice(COLOR_PATCH_BORDER_PX - COLOR_PATCH_SHIFT_PX,
                    stop - COLOR_PATCH_SHIFT_PX)
    source = image.astype(np.float32)
    patch = source[rows, columns, :].copy()
    patch[..., COLOR_PATCH_CHANNEL] = source[rows, shifted,
                                             COLOR_PATCH_CHANNEL]
    rng = np.random.default_rng(COLOR_PATCH_SEED)
    patch = patch + rng.normal(0.0, COLOR_PATCH_NOISE_SD, patch.shape)
    out = source.copy()
    out[rows, columns, :] = patch
    return np.round(np.clip(out, 0, 255)).astype(np.uint8)


@pytest.fixture(scope="session")
def sim_color_local_patch(sim_color: _h3_sims.SimCapture,
                          sim_root: Path) -> _h3_sims.SimCapture:
    import tifffile

    target = (sim_root / "local-patch"
              / "sim-color-local-patch-1200dpi.tiff")
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(
            target, _color_patch_raster(tifffile.imread(sim_color.tiff)))
    return _h3_sims.SimCapture(
        name="color-local-patch", format_ref=sim_color.format_ref,
        dpi=sim_color.dpi, rot_k=0, tiff=target,
        tiff_sha256=_h3_sims.sha256_file(target), payload=sim_color.payload,
        payload_sha256=sim_color.payload_sha256,
        payload_bytes=sim_color.payload_bytes, emit_dir=sim_color.emit_dir)


# The colour-patch decodes are the widened matrix, not the ordinary sim
# lane: measured 2026-08-30 they cost ~490 s of a 140 s budget on a
# loaded machine (the K trio costs ~130 s).  Their goldens are pinned in
# test_h3_plugins_local_ctx.py either way; one deleted line each puts
# them back in the slow lane.
COLOR_PATCH_LANE = "the colour local-head existence proof"

# The residue tier, as this base carries it.  The existence proof's
# control drops the WHOLE tier, because after `tiles.planek` merged no
# single row is load-bearing on its own — see the 2026-08-31 episode in
# test_h3_plugins_local_ctx.py.  A row added to the tier belongs here,
# and the module's own cross-row pins fail loudly until it is.
COLOR_PATCH_RESIDUE_TIER = ("tiles.local", "tiles.planek",
                            "tiles.uplift", "tiles.swim")


@pytest.fixture(scope="session")
def decode_color_local_patch_w1(sim_color_local_patch: _h3_sims.SimCapture,
                                decode_root: Path) -> DecodeRecord:
    _h3_support.skip_unless_oracle_sweeps(COLOR_PATCH_LANE)
    return _decode_once("color-local-patch-w1", sim_color_local_patch,
                        decode_root, workers=1,
                        extra_argv=("--complete", "--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_color_local_patch_off_w1(
        sim_color_local_patch: _h3_sims.SimCapture,
        decode_root: Path) -> DecodeRecord:
    """The tree with `tiles.local` alone removed — the OVERLAP witness.

    Not the existence proof's control any more: `tiles.planek` steps
    into the gap here and mints the same six certificates.  Kept because
    that substitution is the whole 2026-08-31 episode and it has to stay
    measured rather than remembered.
    """
    _h3_support.skip_unless_oracle_sweeps(COLOR_PATCH_LANE)
    return _decode_once("color-local-patch-off-w1", sim_color_local_patch,
                        decode_root, workers=1,
                        extra_argv=("--complete", "--max-pages", "1"),
                        drop_rows=("tiles.local",))


@pytest.fixture(scope="session")
def decode_color_local_patch_no_residue_w1(
        sim_color_local_patch: _h3_sims.SimCapture,
        decode_root: Path) -> DecodeRecord:
    """The tree with the WHOLE residue tier removed — the control.

    What the existence proof is entitled to claim once two rows can do
    the same job: that the tier collectively earns these certificates,
    not that any one row exclusively does.
    """
    _h3_support.skip_unless_oracle_sweeps(COLOR_PATCH_LANE)
    return _decode_once("color-local-patch-no-residue-w1",
                        sim_color_local_patch, decode_root, workers=1,
                        extra_argv=("--complete", "--max-pages", "1"),
                        drop_rows=COLOR_PATCH_RESIDUE_TIER)


@pytest.fixture(scope="session")
def decode_color_local_patch_w8(sim_color_local_patch: _h3_sims.SimCapture,
                                decode_root: Path) -> DecodeRecord:
    _h3_support.skip_unless_oracle_sweeps(COLOR_PATCH_LANE)
    return _decode_once("color-local-patch-w8", sim_color_local_patch,
                        decode_root, workers=8,
                        extra_argv=("--complete", "--max-pages", "1"))


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


@dataclass(frozen=True)
class DecodeRecord:
    label: str
    format_ref: str
    rot_k: int
    workers: int
    argv: tuple[str, ...]
    exit_code: int
    status: str
    payload: bytes | None
    payload_sha256: str | None
    certified: int
    certificates: dict
    certificate_signature: tuple
    events: tuple
    report: dict
    run_dir: Path
    out_path: Path
    out_exists: bool
    stdout: str
    stderr: str
    wall_s: float
    union_subjects: tuple = ()
    attempt_outcomes: dict = dataclass_field(default_factory=dict)
    engine: object | None = None


def _certificate_signature(certificates: dict) -> tuple:
    rows = []
    for key in sorted(certificates):
        certificate = certificates[key]
        rows.append((tuple(key),
                     np.asarray(certificate.user_bits, np.uint8).tobytes()))
    return tuple(rows)


def _decode_once(label: str, capture: _h3_sims.SimCapture, root: Path,
                 workers: int = 8, extra_argv: tuple[str, ...] = (),
                 drop_rows: tuple[str, ...] = (),
                 keep_engine: bool = False) -> DecodeRecord:
    return _decode_group(label, (capture,), root, workers, extra_argv,
                         drop_rows, keep_engine)


# Labels name run dirs under one session decode_root; a silent reuse is
# refused by the CLI's own overwrite guard 100 seconds into the second
# decode, which reads as a decode regression rather than the harness
# error it is (the color-w1 collision, 2026-08-31).  The registry makes
# it loud and immediate instead.
_DECODE_LABELS_USED: dict[str, str] = {}


def _claim_decode_label(label: str, root: Path) -> None:
    key = f"{root}::{label}"
    holder = _DECODE_LABELS_USED.get(key)
    caller = "conftest/test"
    if holder is not None:
        raise RuntimeError(
            f"duplicate decode label {label!r} under {root} — labels name "
            f"run dirs, so every _decode_once/_decode_group call in a "
            f"session needs its own; pick a distinct label")
    _DECODE_LABELS_USED[key] = caller


def _decode_group(label: str, captures: tuple[_h3_sims.SimCapture, ...],
                  root: Path, workers: int = 8,
                  extra_argv: tuple[str, ...] = (),
                  drop_rows: tuple[str, ...] = (),
                  keep_engine: bool = False) -> DecodeRecord:
    _h3_support.skip_unless_slow_lane(f"the {label} sim decode")
    _claim_decode_label(label, root)
    run_dir_base = root / label / "run"
    run_dir = cli.run_dir_for(run_dir_base)
    out_path = root / label / "payload.bin"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    argv = ("decode", *(str(capture.tiff) for capture in captures),
            *(part for capture in captures
              for part in ("--dpi", str(int(capture.dpi)))),
            "--format", captures[0].format_ref, "--out", str(out_path),
            "--workers", str(workers), "--run-dir", str(run_dir_base),
            *extra_argv)
    captured: dict[str, object] = {}
    original = engine.decode

    def instrumented(request: object,
                     events: list | None = None) -> data.RunResult:
        collected: list = [] if events is None else events
        instance = engine._Engine(request, collected)
        result = instance.run()
        captured["certificates"] = dict(instance._certificates)
        captured["events"] = tuple(collected)
        captured["union_subjects"] = tuple(sorted(
            key[1] for key in instance._bookmarks
            if key[0] == "tiles.union"))
        captured["attempt_outcomes"] = dict(instance._attempt_outcomes)
        if keep_engine:
            captured["engine"] = instance
        return result

    out = io.StringIO()
    err = io.StringIO()
    standing_rows = engine.DESCRIPTORS
    standing_by_name = engine.DESCRIPTOR_BY_NAME
    with _WORK_LOCK:
        engine.decode = instrumented
        if drop_rows:
            rows = tuple(descriptor for descriptor in standing_rows
                         if descriptor.name not in drop_rows)
            assert len(rows) == len(standing_rows) - len(drop_rows), (
                f"drop_rows {drop_rows} does not name live descriptor rows")
            engine.DESCRIPTORS = rows
            engine.DESCRIPTOR_BY_NAME = {descriptor.name: descriptor
                                         for descriptor in rows}
        started = time.monotonic()
        try:
            with (contextlib.redirect_stdout(out),
                  contextlib.redirect_stderr(err)):
                exit_code = cli.main(list(argv))
        finally:
            engine.decode = original
            engine.DESCRIPTORS = standing_rows
            engine.DESCRIPTOR_BY_NAME = standing_by_name
            wall_s = time.monotonic() - started
    certificates = captured.get("certificates", {})
    report_path = run_dir / "report.json"
    report: dict = {}
    if report_path.is_file():
        import json

        report = json.loads(report_path.read_text())
    payload = out_path.read_bytes() if out_path.is_file() else None
    return DecodeRecord(
        label=label, format_ref=captures[0].format_ref,
        rot_k=captures[0].rot_k,
        workers=workers, argv=argv, exit_code=exit_code,
        status="verified" if exit_code == 0 else "not-verified",
        payload=payload,
        payload_sha256=(hashlib.sha256(payload).hexdigest()
                        if payload is not None else None),
        certified=len(certificates), certificates=certificates,
        certificate_signature=_certificate_signature(certificates),
        events=captured.get("events", ()), report=report, run_dir=run_dir,
        out_path=out_path, out_exists=out_path.is_file(),
        stdout=out.getvalue(), stderr=err.getvalue(), wall_s=wall_s,
        union_subjects=captured.get("union_subjects", ()),
        attempt_outcomes=captured.get("attempt_outcomes", {}),
        engine=captured.get("engine"))


@pytest.fixture(scope="session")
def decode_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("h3-decodes")


@pytest.fixture(scope="session")
def decode_k_w1(sim_k: _h3_sims.SimCapture,
                decode_root: Path) -> DecodeRecord:
    return _decode_once("k-w1", sim_k, decode_root, workers=1)


@pytest.fixture(scope="session")
def decode_k_max_pages_1(sim_k: _h3_sims.SimCapture,
                         decode_root: Path) -> DecodeRecord:
    return _decode_once("k-max-pages-1", sim_k, decode_root, workers=1,
                        extra_argv=("--max-pages", "1"))


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
def sim_k_mixed(sim_k: _h3_sims.SimCapture, sim_root: Path,
                ) -> tuple[_h3_sims.SimCapture, _h3_sims.SimCapture]:
    with _WORK_LOCK:
        outdir = _materialise(
            "k-mixed",
            lambda staging: _h3_sims.make_k_mixed(sim_k.tiff, staging),
            _h3_sims.EXPECTED_MIXED, sim_root)
    return _h3_sims.capture_k_mixed(outdir, sim_k)


@pytest.fixture(scope="session")
def sim_color_hard(sim_root: Path,
                   ) -> tuple[_h3_sims.SimCapture, _h3_sims.SimCapture]:
    """The top-rung colour pair: in register, and one plane displaced.

    Kept out of the ordinary sim lane on wall alone — the degraded
    capture's own rescue tiers make it the most expensive decode in the
    tree (measured 2026-08-30: 212 s of CPU at workers 1, against a
    140 s budget for the WHOLE slow lane).
    """
    _sim_gate("the registration-degraded colour pair")
    _h3_support.skip_unless_oracle_sweeps(
        "the registration-degraded colour pair")
    with _WORK_LOCK:
        outdir = _materialise("color-hard", _h3_sims.make_color_hard_pair,
                              _h3_sims.EXPECTED_HARD, sim_root)
    return (_h3_sims.capture_color_hard(outdir, _h3_sims.CONTROL_TIFF_NAME,
                                        "hard-control"),
            _h3_sims.capture_color_hard(outdir, _h3_sims.SHIFTED_TIFF_NAME,
                                        "hard-shifted"))


@pytest.fixture(scope="session")
def sim_color_hard_steep(sim_root: Path,
                         ) -> tuple[_h3_sims.SimCapture, _h3_sims.SimCapture]:
    """The same pair at three dots: the swim's reason to exist.

    Same emit, same shape, same period, same noise draw as
    `sim_color_hard` — only the AMPLITUDE changes, from two dots to
    three.  That one dial is past the window pose search's quarter-cell
    reach and past what the tile-space field's linearised probes recover,
    and it stays inside the swim's one-cell bound.
    """
    _sim_gate("the steeply displaced colour pair")
    _h3_support.skip_unless_oracle_sweeps("the steeply displaced pair")
    with _WORK_LOCK:
        outdir = _materialise("color-hard-steep",
                              _h3_sims.make_color_hard_steep_pair,
                              _h3_sims.EXPECTED_HARD_STEEP, sim_root)
    return (_h3_sims.capture_color_hard(outdir, _h3_sims.CONTROL_TIFF_NAME,
                                        "steep-control"),
            _h3_sims.capture_color_hard(outdir, _h3_sims.SHIFTED_TIFF_NAME,
                                        "steep-shifted"))


@pytest.fixture(scope="session")
def decode_steep_control(decode_hard_control: DecodeRecord) -> DecodeRecord:
    # the steep pair shares its in-register control raster with the
    # two-dot pair (CONTROL_TIFF_SHA256 is pinned in both), same argv,
    # same hold-out: one decode, not two
    return decode_hard_control


@pytest.fixture(scope="session")
def decode_steep_fields(sim_color_hard_steep,
                        decode_root: Path) -> DecodeRecord:
    return _decode_once("steep-fields", sim_color_hard_steep[1],
                        decode_root, workers=1,
                        extra_argv=("--complete", "--plane-fields",
                                    "--max-pages", "1"),
                        drop_rows=("tiles.swim",))


@pytest.fixture(scope="session")
def decode_steep_fields_swim(sim_color_hard_steep,
                             decode_root: Path) -> DecodeRecord:
    return _decode_once("steep-fields-swim", sim_color_hard_steep[1],
                        decode_root, workers=1,
                        extra_argv=("--complete", "--plane-fields",
                                    "--max-pages", "1"))


# `tiles.swim` is HELD OUT of the three field-yield decodes, and the
# same row set is used in all three so the arms differ only in the dial
# and the capture.  Its blind translation bound is one printed CELL —
# 3.000 dots on this c3 page, which is exactly the peak the pair
# injects — so with the field off the row undoes the whole stimulus by
# itself (measured 2026-08-31: 300/300, seven certificates minted by the
# row) and the field has nothing left to buy back.  Every OTHER rescue
# row stays live and keeps working the page.  The ruling, the four
# directions that were measured and failed instead, and the condition
# that expires the hold-out are in test_h3_color_field_yield.py.
FIELD_YIELD_HELD_OUT = ("tiles.swim",)


@pytest.fixture(scope="session")
def decode_hard_control(sim_color_hard, decode_root: Path) -> DecodeRecord:
    return _decode_once("hard-control", sim_color_hard[0], decode_root,
                        workers=1, extra_argv=("--complete", "--max-pages", "1"),
                        drop_rows=FIELD_YIELD_HELD_OUT)


@pytest.fixture(scope="session")
def decode_hard_shifted_off(sim_color_hard,
                            decode_root: Path) -> DecodeRecord:
    return _decode_once("hard-shifted-off", sim_color_hard[1], decode_root,
                        workers=1, extra_argv=("--complete", "--max-pages", "1"),
                        drop_rows=FIELD_YIELD_HELD_OUT)


@pytest.fixture(scope="session")
def decode_hard_shifted_on(sim_color_hard,
                           decode_root: Path) -> DecodeRecord:
    return _decode_once("hard-shifted-on", sim_color_hard[1], decode_root,
                        workers=1,
                        extra_argv=("--complete", "--plane-fields",
                                    "--max-pages", "1"),
                        drop_rows=FIELD_YIELD_HELD_OUT)


@pytest.fixture(scope="session")
def decode_color_w1_fields(sim_color: _h3_sims.SimCapture,
                           decode_root: Path) -> DecodeRecord:
    _h3_support.skip_unless_oracle_sweeps("the dial-on clean colour decode")
    return _decode_once("color-w1-fields", sim_color, decode_root,
                        workers=1,
                        extra_argv=("--complete", "--plane-fields",
                                    "--max-pages", "1"))


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
    return _decode_group("k-mixed-w8", sim_k_mixed, decode_root, workers=8)
