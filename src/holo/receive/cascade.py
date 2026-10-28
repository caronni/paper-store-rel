"""Faithful E023c direct-native scale scheduler.

Every level is derived directly from the authenticated native raster (no
derived level feeds another), runs the typed E021 -> E022 -> E023b lane,
and crosses one atomic retention barrier before the next level begins.  A
crash can repeat only the in-flight level.  A numerical refusal is
retained and the scheduler proceeds finer.  Since v0.37 a derived lane is
streamed once and pooled for the native raster's invocation lifetime
(``DerivedLanePool``); the M-level visit reuses the base visit's exact
derivation, and a parked-empty M-level defers derivation entirely.
"""
from __future__ import annotations

from dataclasses import dataclass
from tempfile import TemporaryFile
from typing import IO, ClassVar
from weakref import WeakKeyDictionary

import numpy as np

from ..format.profiles import Family
from .runtime_model import (
    LaneRequest,
    RasterView,
    ScheduleContext,
)
from .scale_space import (
    ScaleLevel,
    ScaleSchedule,
    area_decimate_into,
    area_decimate_rgb_into,
)
from .types import (
    UPLIFT_ARMS,
    Detail,
    Disposition,
    EventAuthority,
    LaneSpec,
    uplift_lane_id,
)


_VALIDATION_CHUNK_BYTES = 1 << 22


def uplift_arms_for_codec(family: Family, n_streams: int) -> tuple[str, ...]:
    """The supplemental arms a coding schedules, in plan order.

    PER-CODING APPLICABILITY (PK-CLEAN, policy `…-codingaware`).  K
    schedules none.  A colour coding schedules the whole registered tail
    EXCEPT the arms its codec cannot express: A4b conditions a plane's
    marginal on its CERTIFIED SIBLING planes, so a coding that carries a
    single payload stream has no sibling to condition on and the lane is
    a guaranteed zero.  Measured before it was filtered: xerox c3-cmy7's
    `u03-a4b` ran 98 blocks / 185 attempts, emitted not one
    ``color.conditioning.*`` key and minted 0 certificates, for 70 s wall
    / 144 s CPU (COLOR-UPLIFT-MEASUREMENTS §10.3/§10.7).

    The W3 ``field`` arm (PLANE-FIELDS §6.2) is NOT stream-conditional:
    it is dimensioned by PLANES, and every colour family prints three.
    cmy7 rides one stream and gains most per tile — its joint pack7
    symbol is poisoned by any single desynced plane — so the filter
    below deliberately touches only the sibling arm.

    Every codec carries a family now, so dispatch is exact rather than a
    keep-the-tail default for the unrecognized case.
    """
    if family is Family.K:
        return ()
    if n_streams < 2:
        return tuple(arm for arm in UPLIFT_ARMS if arm != _SIBLING_ARM)
    return UPLIFT_ARMS


#: The arm that needs a certified SIBLING plane, hence >= 2 streams.
_SIBLING_ARM = "a4b"


def _scale_diagnostic_snapshot(
    plan: tuple[LaneSpec, ...],
    schedule: ScaleSchedule,
    existing: object | None,
) -> None:
    """No-op since the live-view removal; see _diagnostic_snapshots."""
    del plan, schedule, existing
    return None


class ScaleRaster:
    """Read-only, native-range grey view derived directly from native."""

    def __init__(
        self,
        pixels: np.ndarray,
        source_sha256: str,
        dpi: float,
    ) -> None:
        array = np.asanyarray(pixels)
        if array.ndim != 2 or array.size == 0:
            raise ValueError("scale pixels must be a non-empty grey raster")
        if (not np.issubdtype(array.dtype, np.number)
                or np.issubdtype(array.dtype, np.complexfloating)
                or np.issubdtype(array.dtype, np.bool_)):
            raise ValueError("scale pixels must have a real numeric dtype")
        if (not isinstance(source_sha256, str)
                or len(source_sha256) != 64
                or any(char not in "0123456789abcdef"
                       for char in source_sha256)):
            raise ValueError("scale source must be lowercase SHA-256")
        if (isinstance(dpi, (bool, np.bool_))
                or not np.isfinite(dpi) or dpi <= 0):
            raise ValueError("scale dpi must be finite and positive")
        rows = max(
            1,
            _VALIDATION_CHUNK_BYTES // max(1, int(array[0:1].nbytes)),
        )
        maximum = -np.inf
        for row0 in range(0, array.shape[0], rows):
            block = array[row0:row0 + rows]
            if (np.issubdtype(array.dtype, np.inexact)
                    and not np.isfinite(block).all()):
                raise ValueError("derived scale contains non-finite samples")
            maximum = max(maximum, float(np.max(block)))
        array.setflags(write=False)
        self._pixels: np.ndarray | None = array
        self._source_sha256 = source_sha256
        self._native_dtype = np.dtype(array.dtype)
        self.dpi = float(dpi)
        self.shape = (int(array.shape[0]), int(array.shape[1]))
        self.luma_max = maximum

    @property
    def source_sha256(self) -> str:
        return self._source_sha256

    @property
    def native_dtype(self) -> np.dtype:
        return self._native_dtype

    def _open_pixels(self) -> np.ndarray:
        pixels = self._pixels
        if pixels is None:
            raise RuntimeError("derived scale raster has been released")
        return pixels

    def _release(self) -> None:
        """Invalidate this transient view and close an owned mmap, if any."""
        pixels = self._pixels
        if pixels is None:
            return
        self._pixels = None
        mapping = getattr(pixels, "_mmap", None)
        if mapping is not None and not mapping.closed:
            mapping.close()

    def contains(self, r0: int, r1: int, c0: int, c1: int) -> bool:
        values = (r0, r1, c0, c1)
        if any(isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, np.integer)) for value in values):
            return False
        return (0 <= r0 < r1 <= self.shape[0]
                and 0 <= c0 < c1 <= self.shape[1])

    def crop_native(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        pixels = self._open_pixels()
        if not self.contains(r0, r1, c0, c1):
            raise ValueError("scale crop is not a non-empty in-bounds box")
        result = pixels[r0:r1, c0:c1]
        result.setflags(write=False)
        return result

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        native = self.crop_native(r0, r1, c0, c1)
        result = native.astype(np.float32, copy=False)
        if np.shares_memory(result, native) or not result.flags.c_contiguous:
            result = np.array(result, np.float32, copy=True, order="C")
        result.setflags(write=False)
        return result


class ColorScaleRaster:
    """Read-only aligned RGB view for one provisional color scale lane."""

    def __init__(
        self,
        pixels: np.ndarray,
        source_sha256: str,
        dpi: float,
    ) -> None:
        array = np.asanyarray(pixels)
        if array.ndim != 3 or array.shape[2] != 3 or array.size == 0:
            raise ValueError("color scale pixels must be non-empty RGB")
        if (not np.issubdtype(array.dtype, np.number)
                or np.issubdtype(array.dtype, np.complexfloating)
                or np.issubdtype(array.dtype, np.bool_)):
            raise ValueError("color scale pixels must have a real numeric dtype")
        if (not isinstance(source_sha256, str)
                or len(source_sha256) != 64
                or any(char not in "0123456789abcdef"
                       for char in source_sha256)):
            raise ValueError("scale source must be lowercase SHA-256")
        if (isinstance(dpi, (bool, np.bool_))
                or not np.isfinite(dpi) or dpi <= 0):
            raise ValueError("scale dpi must be finite and positive")
        rows = max(
            1,
            _VALIDATION_CHUNK_BYTES // max(1, int(array[0:1].nbytes)),
        )
        maximum = -np.inf
        for row0 in range(0, array.shape[0], rows):
            block = array[row0:row0 + rows]
            if (np.issubdtype(array.dtype, np.inexact)
                    and not np.isfinite(block).all()):
                raise ValueError("derived color scale contains non-finite samples")
            luma = block.mean(axis=2, dtype=np.float32)
            maximum = max(maximum, float(np.max(luma)))
        array.setflags(write=False)
        self._pixels: np.ndarray | None = array
        self._source_sha256 = source_sha256
        self._native_dtype = np.dtype(array.dtype)
        self.dpi = float(dpi)
        self.shape = (int(array.shape[0]), int(array.shape[1]))
        self.luma_max = maximum

    @property
    def source_sha256(self) -> str:
        return self._source_sha256

    @property
    def native_dtype(self) -> np.dtype:
        return self._native_dtype

    def _open_pixels(self) -> np.ndarray:
        pixels = self._pixels
        if pixels is None:
            raise RuntimeError("derived color scale raster has been released")
        return pixels

    def _release(self) -> None:
        pixels = self._pixels
        if pixels is None:
            return
        self._pixels = None
        mapping = getattr(pixels, "_mmap", None)
        if mapping is not None and not mapping.closed:
            mapping.close()

    def contains(self, r0: int, r1: int, c0: int, c1: int) -> bool:
        values = (r0, r1, c0, c1)
        if any(isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, np.integer)) for value in values):
            return False
        return (0 <= r0 < r1 <= self.shape[0]
                and 0 <= c0 < c1 <= self.shape[1])

    def crop_native(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        pixels = self._open_pixels()
        if not self.contains(r0, r1, c0, c1):
            raise ValueError("color scale crop is not a non-empty in-bounds box")
        result = pixels[r0:r1, c0:c1]
        result.setflags(write=False)
        return result

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        native = self.crop_native(r0, r1, c0, c1)
        result = native.mean(axis=2, dtype=np.float32)
        if not result.flags.c_contiguous:
            result = np.array(result, np.float32, copy=True, order="C")
        result.setflags(write=False)
        return result


def lane_kind(lane: LaneSpec) -> str:
    """The lane's plan class: ordinary / mopup / refine / uplift:<arm>.

    One vocabulary, used by the scheduler's events, the diagnostics rows
    and the campaign harness, so a reader never has to reconstruct the
    class from three optional fields.
    """
    if lane.mopup_of is not None:
        return "mopup"
    if lane.refine_of is not None:
        return "refine"
    arm = lane.arm_override
    return "ordinary" if arm is None else f"uplift:{arm}"


def _scale_plan(
    schedule: ScaleSchedule, *,
    codec_family: Family = Family.K,
    n_streams: int = 1,
) -> tuple[LaneSpec, ...]:
    rows: list[LaneSpec] = []
    for level in schedule.levels:
        scale = level.transform.source_per_output
        rows.append(LaneSpec(
            lane_id=level.label,
            target_ppc_num=level.ppc.numerator,
            target_ppc_den=level.ppc.denominator,
            native_per_view_num=scale.numerator,
            native_per_view_den=scale.denominator,
            parent_lane_id=None if not rows else rows[-1].lane_id,
        ))
    # v0.33: one mop-up entry per ladder lane, appended after native in
    # coarse->fine order.  A mop-up shares its base lane's exact ratios
    # (same raster derivation) and evidence identity via ``mopup_of``;
    # its own lane_id stays unique for plan/artifact namespaces.
    ladder = tuple(rows)
    for base in ladder:
        rows.append(LaneSpec(
            lane_id="m" + base.lane_id[1:],
            target_ppc_num=base.target_ppc_num,
            target_ppc_den=base.target_ppc_den,
            native_per_view_num=base.native_per_view_num,
            native_per_view_den=base.native_per_view_den,
            parent_lane_id=rows[-1].lane_id,
            mopup_of=base.lane_id,
        ))
    # v0.42: one refinement entry per ladder lane, appended after ALL
    # M-levels, coarse->fine.  R(Lk) binds to Lk's exact transform (same
    # raster derivation) but owns its OWN evidence namespace — only
    # certificates cross lanes.  The full plan is
    # [L0..Ln, M(L0)..M(Ln), R(L0)..R(Ln)] for K and
    # [L0..Ln, M(L0)..M(Ln), R(L0)..R(Ln),
    #  U(Ln,off), U(Ln,a3), U(Ln,a4b), U(Ln,field)]
    # for a multi-stream colour coding (cmy7 drops the a4b entry only).
    for base in ladder:
        rows.append(LaneSpec(
            lane_id="r" + base.lane_id[1:],
            target_ppc_num=base.target_ppc_num,
            target_ppc_den=base.target_ppc_den,
            native_per_view_num=base.native_per_view_num,
            native_per_view_den=base.native_per_view_den,
            parent_lane_id=rows[-1].lane_id,
            refine_of=base.lane_id,
        ))
    # PK4.3 supplemental lanes, COLOR ONLY, appended after the whole
    # standard l/m/r sequence: one per APPLICABLE override
    # (:func:`uplift_arms_for_codec`), in ``UPLIFT_ARMS`` order, all bound
    # to the FINEST ordinary rung.  PK5 made the first of them ``off`` —
    # the pre-campaign BASELINE path over the residue, so a
    # ladder-configuration change cannot strand a tile the old
    # configuration would have certified (``lane_uplift``).
    #
    # Why the finest rung, and why exactly one lane per arm.  A u-lane
    # exists to re-read the residue that survived every earlier barrier —
    # by construction the hardest tiles on the page — so it should read
    # them through the best evidence the capture has, and that is
    # unambiguously the largest px/cell footing (the campaign's own
    # measured law that sampling, not the detector, sets the color floor:
    # COLOR-UPLIFT-MEASUREMENTS §8.4 / e023c decimation doctrine).  It is
    # also the only capture-independent choice: a per-capture footing
    # would be a swept constant, and the whole point of the supplemental
    # form is that it has NO tuning surface.
    if ladder:
        finest = ladder[-1]
        for arm in uplift_arms_for_codec(codec_family, n_streams):
            rows.append(LaneSpec(
                lane_id=uplift_lane_id(finest.lane_id, arm),
                target_ppc_num=finest.target_ppc_num,
                target_ppc_den=finest.target_ppc_den,
                native_per_view_num=finest.native_per_view_num,
                native_per_view_den=finest.native_per_view_den,
                parent_lane_id=rows[-1].lane_id,
            ))
    return tuple(rows)


def scale_plan(
    native_dpi: float, cell_dots: int, *,
    codec_family: Family = Family.K,
    n_streams: int = 1,
) -> tuple[LaneSpec, ...]:
    """Return the stable exact-rational lane plan for one capture.

    ``codec_family``/``n_streams`` select the lane classes the coding
    schedules: K gets ``[L…, M…, R…]`` exactly as before, a color coding
    additionally gets the supplemental tail its codec can use
    (:func:`uplift_arms_for_codec`).  The default is K so a caller that
    has no spec in hand cannot silently mint color lanes.
    """
    return _scale_plan(
        ScaleSchedule.auto(native_dpi, cell_dots),
        codec_family=codec_family, n_streams=n_streams)


class DerivedLanePool:
    """Invocation-lifetime cache of derived lane rasters for one capture.

    v0.37 (plan 3.4): a derived lane is streamed once into its disk-backed
    mmap and retained for the native raster's invocation lifetime, keyed
    by (lane label, derivation kind).  The M-level visit therefore reuses
    the base visit's derivation instead of re-reading native.  Derivation
    is a pure function of the frozen authenticated native raster, so reuse
    is bit-exact by construction.  File-backed mmaps carry no RSS concern;
    the runtime releases every pool explicitly at the end of the drive.
    """

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[
            tuple[str, str],
            tuple[IO[bytes], ScaleRaster | ColorScaleRaster],
        ] = {}

    def get(
        self, key: tuple[str, str],
    ) -> ScaleRaster | ColorScaleRaster | None:
        entry = self._entries.get(key)
        return None if entry is None else entry[1]

    def put(
        self,
        key: tuple[str, str],
        artifact: IO[bytes],
        raster: ScaleRaster | ColorScaleRaster,
    ) -> None:
        if key in self._entries:
            raise ValueError(f"derived lane {key} is already pooled")
        self._entries[key] = (artifact, raster)

    def release(self) -> None:
        for artifact, raster in self._entries.values():
            raster._release()
            artifact.close()
        self._entries.clear()


_DERIVED_POOLS: WeakKeyDictionary = WeakKeyDictionary()


def _pool_for(native: RasterView) -> DerivedLanePool:
    pool = _DERIVED_POOLS.get(native)
    if pool is None:
        pool = DerivedLanePool()
        _DERIVED_POOLS[native] = pool
    return pool


def release_derived_lanes(native: RasterView) -> None:
    """Free every pooled derived-lane raster of one native capture."""
    pool = _DERIVED_POOLS.pop(native, None)
    if pool is not None:
        pool.release()


def _derivation_kind(context: ScheduleContext) -> str:
    """Pool-key derivation kind; mirrors ``_derive_level``'s predicate."""
    return (
        "rgb"
        if context.spec.codec_family is not Family.K
        and context.facts.channels == 3
        else "grey"
    )


def _derive_level(
    context: ScheduleContext,
    level: ScaleLevel,
) -> tuple[IO[bytes], ScaleRaster | ColorScaleRaster]:
    """Stream one derived lane directly into a disk-backed mmap (exact).

    Native remains the authenticated ingest object.  K retains the exact
    registered RGB->raw-luma operation; explicit color rows instead
    preserve three aligned channels and derive luma from that lane.  In
    both cases no derived level feeds another.
    """
    native = context.native
    height, width = native.shape
    source = native.crop_native(0, height, 0, width)
    shape_yx = level.transform.output_shape(source.shape)
    if min(shape_yx, default=0) < 1:
        raise ValueError(
            f"capture is too small for complete pixels at {level.label}")
    color_rgb = (
        context.spec.codec_family is not Family.K
        and source.ndim == 3
    )
    shape = shape_yx + ((3,) if color_rgb else ())
    artifact = TemporaryFile(prefix="holo-scale-", suffix=".dat")
    pixels: np.ndarray | None = None
    try:
        pixels = np.memmap(
            artifact, mode="w+", dtype=source.dtype, shape=shape,
        )
        if color_rgb:
            area_decimate_rgb_into(source, level.transform, pixels)
            raster: ScaleRaster | ColorScaleRaster = ColorScaleRaster(
                pixels,
                context.facts.source_sha256,
                float(level.dpi),
            )
        else:
            area_decimate_into(source, level.transform, pixels)
            raster = ScaleRaster(
                pixels,
                context.facts.source_sha256,
                float(level.dpi),
            )
    except BaseException:
        mapping = None if pixels is None else getattr(pixels, "_mmap", None)
        if mapping is not None and not mapping.closed:
            mapping.close()
        artifact.close()
        raise
    return artifact, raster


class LazyDerivedRaster:
    """Metadata-complete derived-lane stand-in deferring the pixel stream.

    A parked-empty M-level has no pixel consumer on any production path
    (its survey, address, and payload stages all complete empty without a
    raster read — PAYLOAD-IMPROVEMENTS 6.3), so its visit should not pay
    the full native re-read.  Identity, dpi, shape, and dtype are exact by
    construction from the authenticated facts and the exact-rational
    transform; any unexpected pixel access derives the real raster through
    the pool, so the skip is exactness-preserving by construction.
    """

    __slots__ = (
        "_context", "_level", "_pool", "_key", "_real",
        "dpi", "shape", "_source_sha256", "_dtype",
    )

    def __init__(
        self,
        context: ScheduleContext,
        level: ScaleLevel,
        pool: DerivedLanePool,
        key: tuple[str, str],
    ) -> None:
        self._context = context
        self._level = level
        self._pool = pool
        self._key = key
        self._real: ScaleRaster | ColorScaleRaster | None = None
        self.dpi = float(level.dpi)
        self.shape = level.transform.output_shape(context.facts.shape_yx)
        self._source_sha256 = context.facts.source_sha256
        self._dtype = np.dtype(context.native.native_dtype)

    @property
    def source_sha256(self) -> str:
        return self._source_sha256

    @property
    def native_dtype(self) -> np.dtype:
        return self._dtype

    @property
    def luma_max(self) -> float:
        return self._materialized().luma_max

    def _materialized(self) -> ScaleRaster | ColorScaleRaster:
        if self._real is None:
            cached = self._pool.get(self._key)
            if cached is None:
                artifact, cached = _derive_level(self._context, self._level)
                self._pool.put(self._key, artifact, cached)
            self._real = cached
        return self._real

    def contains(self, r0: int, r1: int, c0: int, c1: int) -> bool:
        values = (r0, r1, c0, c1)
        if any(isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, np.integer)) for value in values):
            return False
        return (0 <= r0 < r1 <= self.shape[0]
                and 0 <= c0 < c1 <= self.shape[1])

    def crop_native(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        return self._materialized().crop_native(r0, r1, c0, c1)

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        return self._materialized().crop_luma(r0, r1, c0, c1)


def _materialize(
    context: ScheduleContext,
    level: ScaleLevel,
    *,
    defer_pixels: bool = False,
) -> RasterView:
    """Return one lane raster, pooled for the native raster's lifetime.

    The first visit of a derived level streams it into a disk-backed mmap
    and pools it; every later visit of the same (label, kind) — the
    M-level in particular — reuses that exact derivation with zero new
    native reads.  ``defer_pixels`` (a parked-empty M-level on a resumed
    invocation) returns a metadata-complete lazy stand-in that derives
    only if a consumer actually reads pixels.
    """
    native = context.native
    if level.is_native:
        return native
    pool = _pool_for(native)
    key = (level.label, _derivation_kind(context))
    cached = pool.get(key)
    if cached is not None:
        return cached
    if defer_pixels:
        return LazyDerivedRaster(context, level, pool, key)
    artifact, raster = _derive_level(context, level)
    pool.put(key, artifact, raster)
    return raster


@dataclass(frozen=True, slots=True)
class PhasedSessionScheduler:
    """v0.33 one-level executor under the runtime's session phase driver.

    The runtime owns cross-capture iteration (rung-major by target ppc,
    then the priced mop-up tail, then — under ``--refine`` — refinement
    levels and, on a color coding, the PK4.3 supplemental tail;
    RECEIVE-DESIGN §8); one ``process`` call advances exactly the
    capture's next plan level and returns.  A mop-up, refinement or
    supplemental level materializes its base lane's raster — the same
    exact-rational transform, keyed by the base lane label
    (``LaneSpec.base_lane_id``).
    """

    policy_id: ClassVar[str] = (
        "holo/phased-session/rung-major-v5-u-lanes-codingaware-field")

    def process(self, context: ScheduleContext) -> None:
        schedule = ScaleSchedule.auto(
            context.native.dpi, context.spec.cell_dots)
        plan = _scale_plan(
            schedule,
            codec_family=context.spec.codec_family,
            n_streams=context.spec.n_streams,
        )
        existing = context.existing_capture
        if existing is not None and existing.plan != plan:
            raise ValueError("persisted capture has a different scale plan")
        ordinal = 0 if existing is None else len(existing.levels)
        if ordinal >= len(plan):
            return
        if ordinal == 0:
            context.progress(
                "scale.plan",
                details=(Detail("level.total", len(plan)),
                         Detail("level.completed", ordinal)),
                snapshot_factory=lambda: _scale_diagnostic_snapshot(
                    plan, schedule, existing),
            )
        lane = plan[ordinal]
        by_label = {level.label: level for level in schedule.levels}
        level = by_label[lane.base_lane_id]
        context.progress(
            "level.open",
            details=(Detail("lane.id", lane.lane_id),
                     Detail("lane.parent_id", lane.parent_lane_id),
                     # PK4.3: the lane CLASS, and for a supplemental lane
                     # the forced arm, on the level's own open event — a
                     # diag row must never have to infer either.
                     Detail("lane.kind", lane_kind(lane)),
                     Detail("lane.arm_override", lane.arm_override),
                     Detail("level.ordinal", ordinal),
                     Detail("level.total", len(plan)),
                     Detail("level.ppc.num", lane.target_ppc_num),
                     Detail("level.ppc.den", lane.target_ppc_den),
                     Detail("level.effective_dpi", float(level.dpi)),
                     # The lane's own pixel scale, so an observer can lift
                     # this level's geometry into capture-native pixels.
                     # M/R lanes carry their BASE lane's ratio verbatim
                     # (``_scale_plan``) because they reuse its raster.
                     Detail("lane.native_per_view.num",
                            lane.native_per_view_num),
                     Detail("lane.native_per_view.den",
                            lane.native_per_view_den)),
        )
        # Parked-emptiness is consulted BEFORE first materialization
        # (PAYLOAD-IMPROVEMENTS 6.3): a parked-empty M-level has no pixel
        # consumer, so its raster stays a lazy metadata stand-in unless
        # the base derivation is already pooled.  The evidence hoist is
        # exact — ``evidence_for`` is a pure read of committed state.
        # v0.42: an R-level ALWAYS runs behind the lazy stand-in — with no
        # eligible work (no certificates yet, or no uncertified tiles) no
        # consumer reads pixels and no raster ever materializes; when the
        # refinement leaves do read, the stand-in derives (or reuses the
        # pooled base derivation) exactly then.
        # v0.51 (PK4.3): a U-level defers for the same reason an R-level
        # does — its pre-gates (force-null, no certificates, no committed
        # poses, every committed span certified) are all pixel-free, so a
        # supplemental lane with nothing to add never derives a raster.
        evidence = context.evidence_for(lane)
        defer_pixels = (
            lane.refine_of is not None
            or lane.uplift_of is not None
            or (lane.mopup_of is not None and not evidence.parked))
        raster = _materialize(context, level, defer_pixels=defer_pixels)
        request = LaneRequest(lane, raster)
        execution = context.run_lane(request, evidence)
        record, delta = execution.durable()
        context.commit(record, delta)
        context.progress(
            "level.complete" if execution.disposition
            is Disposition.COMPLETE else "level.refused",
            details=(Detail("lane.id", lane.lane_id),
                     Detail("level.ordinal", ordinal)),
            authority=EventAuthority.COMMITTED,
        )


__all__ = [
    "ColorScaleRaster", "DerivedLanePool", "LazyDerivedRaster",
    "PhasedSessionScheduler",
    "ScaleRaster", "lane_kind", "release_derived_lanes", "scale_plan",
]
