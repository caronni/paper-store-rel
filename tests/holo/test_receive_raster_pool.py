"""v0.37 derived-lane raster lifetime pins (PAYLOAD-REWORK-PLAN 3.4).

A derived lane is streamed once per invocation into its disk-backed mmap
and pooled for the native raster's lifetime; the M-level visit reuses the
base visit's exact derivation (zero new native reads), and a parked-empty
M-level defers derivation entirely (PAYLOAD-IMPROVEMENTS 6.3).  Every pin
keeps the naive re-derivation as a test-local oracle and asserts byte
identity (the test_cold_search_exactness precedent).
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from holo.format.profiles import Family
from holo.receive import cascade, scan
from holo.receive.cascade import (
    LazyDerivedRaster,
    ScaleRaster,
    _materialize,
    release_derived_lanes,
    scale_plan,
)
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.scale_space import ScaleSchedule, area_decimate
from holo.receive.scan import open_capture
from holo.receive.session import CaptureStatus


def _stub_context(source: np.ndarray, dpi: float = 1200.0):
    native = open_capture(source, dpi)
    facts = SimpleNamespace(
        source_sha256=native.source.sha256,
        channels=native.source.channels,
        shape_yx=native.source.shape,
    )
    return native, SimpleNamespace(
        native=native,
        spec=SimpleNamespace(codec_id="k-v1", codec_family=Family.K,
                             n_streams=1),
        facts=facts)


def _count_derivations(monkeypatch) -> list[int]:
    counter = [0]
    naive = cascade._derive_level

    def counting(context, level):
        counter[0] += 1
        return naive(context, level)

    monkeypatch.setattr(cascade, "_derive_level", counting)
    return counter


def test_pool_reuse_is_the_exact_object_and_byte_identical_to_naive(
    monkeypatch,
) -> None:
    rng = np.random.default_rng(0x37A)
    source = rng.integers(0, 256, (47, 53), dtype=np.uint8)
    native, context = _stub_context(source)
    level = ScaleSchedule.auto(1200, 3).levels[0]
    derivations = _count_derivations(monkeypatch)
    oracle = area_decimate(source, level.transform)  # test-local naive path

    first = _materialize(context, level)
    assert type(first) is ScaleRaster
    height, width = first.shape
    pixels = np.array(first.crop_native(0, height, 0, width), copy=True)
    assert np.array_equal(pixels, oracle)
    assert derivations[0] == 1

    # Repeat visit (the M-level shape): the SAME pooled object, zero new
    # derivations, and therefore zero new native reads.
    assert _materialize(context, level) is first
    assert derivations[0] == 1

    # Release, then re-derive: byte-identical to the pooled content.
    release_derived_lanes(native)
    with pytest.raises(RuntimeError, match="released"):
        first.crop_native(0, 1, 0, 1)
    second = _materialize(context, level)
    assert second is not first
    assert derivations[0] == 2
    assert np.array_equal(
        second.crop_native(0, height, 0, width), pixels)
    assert second.crop_native(0, height, 0, width).tobytes() == (
        pixels.tobytes())
    release_derived_lanes(native)


def test_parked_empty_defer_skips_derivation_until_pixels_are_read(
    monkeypatch,
) -> None:
    rng = np.random.default_rng(0x37B)
    source = rng.integers(0, 256, (47, 53), dtype=np.uint8)
    native, context = _stub_context(source)
    level = ScaleSchedule.auto(1200, 3).levels[0]
    derivations = _count_derivations(monkeypatch)
    oracle = area_decimate(source, level.transform)

    lazy = _materialize(context, level, defer_pixels=True)
    assert isinstance(lazy, LazyDerivedRaster)
    # Metadata is exact without any derivation.
    assert derivations[0] == 0
    assert lazy.source_sha256 == native.source.sha256
    assert lazy.dpi == float(level.dpi)
    assert tuple(lazy.shape) == oracle.shape
    assert np.dtype(lazy.native_dtype) == oracle.dtype
    assert lazy.contains(0, 1, 0, 1)
    assert not lazy.contains(0, 0, 0, 1)

    # Exactness by construction: an actual pixel read derives through the
    # pool and every later visit reuses that derivation.
    height, width = lazy.shape
    assert np.array_equal(lazy.crop_native(0, height, 0, width), oracle)
    assert derivations[0] == 1
    pooled = _materialize(context, level)
    assert type(pooled) is ScaleRaster
    assert np.array_equal(pooled.crop_native(0, height, 0, width), oracle)
    assert derivations[0] == 1
    release_derived_lanes(native)


def test_phased_run_derives_each_lane_once_and_releases_at_drive_end(
    tmp_path, monkeypatch,
) -> None:
    """End-to-end: M-level visits perform zero new derivations or native
    reads, and the runtime frees every pooled derivation at drive end."""
    import _qualify_runtime_fixtures as fixtures

    image = tmp_path / "capture.png"
    fixtures._write_image(image, 61_001)
    spec = fixtures._spec()
    plan = scale_plan(1200.0, spec.cell_dots)
    base = [lane for lane in plan
            if lane.mopup_of is None and lane.refine_of is None]
    derived_labels = {
        lane.lane_id for lane in base
        if lane.native_per_view_num != lane.native_per_view_den}
    # v0.42 plan shape: [L0..Ln, M(L0)..M(Ln), R(L0)..R(Ln)].
    assert derived_labels and len(plan) == 3 * len(base)

    derivations = _count_derivations(monkeypatch)
    native_reads = [0]
    naive_crop = scan.Raster.crop_native

    def counting_crop(self, r0, r1, c0, c1):
        native_reads[0] += 1
        return naive_crop(self, r0, r1, c0, c1)

    monkeypatch.setattr(scan.Raster, "crop_native", counting_crop)

    contexts = []
    pipeline, _calls = fixtures._pipeline(contexts=contexts)
    result = run_receive(
        ReceiveRequest(spec, (fixtures._capture(image),),
                       tmp_path / "state.json", run_refine=True),
        pipeline=pipeline)

    assert result.captures[0].status is CaptureStatus.COMPLETE
    assert len(contexts) == len(plan)
    # Each derived base lane streamed exactly once; every M-level visit
    # reused the pooled derivation and every R-level visit stayed lazy
    # (zero extra derivations), and the only full-frame native reads are
    # those derivations.
    assert derivations[0] == len(derived_labels)
    assert native_reads[0] == derivations[0]
    # The runtime released the pool when the drive ended.
    for context in contexts:
        if type(context.raster) is ScaleRaster:
            with pytest.raises(RuntimeError, match="released"):
                context.raster.crop_native(0, 1, 0, 1)


def test_resumed_parked_empty_mopup_levels_never_materialize(
    tmp_path, monkeypatch,
) -> None:
    """Resume after the base rungs: the parked-empty M-levels complete with
    the lazy stand-in and the invocation performs ZERO derivations."""
    import _qualify_runtime_fixtures as fixtures

    image = tmp_path / "capture.png"
    fixtures._write_image(image, 61_002)
    spec = fixtures._spec()
    plan = scale_plan(1200.0, spec.cell_dots)
    native_base = next(
        lane for lane in plan
        if lane.mopup_of is None
        and lane.native_per_view_num == lane.native_per_view_den)
    state_path = tmp_path / "state.json"

    # Invocation 1 crashes at the native base lane: every coarser base
    # level is committed, no M-level has run yet.
    crashing, _calls = fixtures._pipeline(crash_lane=native_base.lane_id)
    with pytest.raises(RuntimeError, match="between barriers"):
        run_receive(
            ReceiveRequest(spec, (fixtures._capture(image),), state_path),
            pipeline=crashing)

    # Invocation 2: the native base level needs no derivation, every
    # M-level is parked-empty, and every R-level is lazy by construction
    # (v0.42) — nothing materializes at all.
    derivations = _count_derivations(monkeypatch)
    contexts = []
    resumed, _resumed_calls = fixtures._pipeline(contexts=contexts)
    result = run_receive(
        ReceiveRequest(spec, (fixtures._capture(image),), state_path,
                       run_refine=True),
        pipeline=resumed)

    assert result.captures[0].status is CaptureStatus.COMPLETE
    assert len(result.state.captures[0].levels) == len(plan)
    assert derivations[0] == 0
    lazy_lanes = [
        context.lane.lane_id for context in contexts
        if isinstance(context.raster, LazyDerivedRaster)]
    assert lazy_lanes == [
        lane.lane_id for lane in plan
        if (lane.mopup_of is not None or lane.refine_of is not None)
        and lane.native_per_view_num != lane.native_per_view_den]
