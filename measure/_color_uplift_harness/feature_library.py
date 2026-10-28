"""The feature library: sweep-scale iteration without the raster.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.feature_library dump \
            --capture xerox-c3-cmy7 --arm libdump
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.feature_library run \
            --capture xerox-c3-cmy7 --arm parked
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.feature_library run \
            --capture hp-c3-cmy8 --lane l00-2ppc-400dpi \
            --lane l01-4ppc-800dpi --window-phot 20,0.0

WHAT IT IS.  A committed-pose replay (:mod:`replay`, imported and never
modified) spends most of its CPU turning pixels into features: the window
crops, the aperture filter, the point sampling, the registration NCC, and
the corrected re-sample.  None of that depends on which ARM the ladder
then selects.  ``dump`` runs one replay with recording shims around
exactly those functions and persists what they returned; ``run`` replays
again with SERVING shims and no raster at all, so the whole stack —
``fit_region_stack``, the cmy7 head, emission, blocks, the LDPC attempt
engine, per-lane certificate accumulation — executes on the real
production code at a fraction of the cost.

THE TIER LAW.  The library gates ITERATION only.  A committed-pose replay
gates a merge.  A FULL decode gates a bar.  Nothing measured here is a
qualification number, and a library run that cannot be reproduced by its
replay is a library bug, not a finding.

WHAT MAKES IT EXACT, AND WHERE IT REFUSES.  Two invariants.

1. **Producer identity.**  Every shimmed function's module is hashed into
   the library key (``PRODUCER_MODULES``: the feature path plus the two
   shadowed geometry seams).  The iteration surface (``color_stack``,
   ``color_locality``, ``color_fitting``, ``color_calibration``) is
   deliberately NOT hashed: moving it is the whole point.  Edit a
   producer and every library refuses.
2. **The prior-barrier frontier.**  ``build_known_rows`` and the emission
   masks are functions of the certificates minted by EARLIER lanes, so a
   lane's features are only valid while that frontier is unchanged.  The
   dump records each lane's exact prior certificate-ID set and ``run``
   compares before it executes the lane.  A sweep that changes lane N's
   output therefore runs lane N+1 only if the change was empty there;
   otherwise the run STOPS at that lane and says which one.  (Measured
   example: on hp c3-cmy8 A3's region gate refuses at l00 at every swept
   point, so l00 is bit-identical and l01 is a legal sweep target —
   COLOR-UPLIFT-MEASUREMENTS §5.2 finding 3.)

Every lookup is content-addressed over the shimmed call's own inputs, so
a served value can only ever be the one the recorded call produced.  A
miss is a hard refusal, never a silent recomputation — the run has no
raster to recompute from.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import platform
import resource
import subprocess
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import corpus, state_cache
from .corpus import CaptureRow
from .replay import replay_lanes

LIBRARY_SCHEMA = "color-uplift-feature-library-1"
# The PRODUCER set: every module whose output a feature library shadows.
# Hashing these and NOT the arm ladder is what lets a library survive an
# iteration and refuse a producer change.
PRODUCER_MODULES = (
    "color_sampling.py", "color_anchoring.py", "known_field.py",
    "color_payload.py", "place.py", "color_refine.py",
)
# The ARM ladder: the iteration surface.  Never part of a library's
# validity key (moving it is the point), always REPORTED, because a
# fidelity claim — "the library reproduced the replay" — is only about
# one arm if both ran the same arm code.
ARM_MODULES = (
    "color_stack.py", "color_locality.py", "color_fitting.py",
    "color_calibration.py", "color_conditioning.py", "color_context.py",
    "color_neighbourhood.py",
)
SRC_RECEIVE = Path(__file__).resolve().parents[2] / "src" / "holo" / "receive"


def producer_identity() -> str:
    """SHA-256 over the source text of the shadowed feature path."""
    return _source_identity(PRODUCER_MODULES)


def _git(*args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, check=True).stdout.strip()


def _source_identity(names: tuple[str, ...]) -> str:
    """SHA-256 over the SOURCE TEXT of the named receiver modules."""
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode())
        digest.update((SRC_RECEIVE / name).read_bytes())
    return digest.hexdigest()


def _receiver_tree_sha256() -> str:
    """SHA-256 over every source file under ``src/holo`` — content only."""
    digest = hashlib.sha256()
    root = SRC_RECEIVE.parent
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def tree_state() -> dict:
    """Identify the exact code this process is about to import.

    HEAD is not the code.  This worktree is shared with other campaign
    workers whose uncommitted diff IS the code under test, and it can be
    swapped out mid-flight: on 2026-08-08 a concurrent ``git stash
    push``/``pop`` (10:47-10:49) invalidated every run started in that
    window, and a concurrent COMMIT at 11:07 moved HEAD and emptied the
    diff without changing one byte of source.  A git-shaped fingerprint
    gets the first case right and the second one wrong, so the load-
    bearing field here is a CONTENT hash of ``src/holo``; the git fields
    ride along as context, never as the test.

    A run records this at entry and at exit.  Different snapshots mean
    the code moved under the run and the result is void.
    """
    status = _git("status", "--porcelain")
    return {
        "receiver_tree_sha256": _receiver_tree_sha256(),
        "producer_identity": _source_identity(PRODUCER_MODULES),
        "arm_identity": _source_identity(ARM_MODULES),
        "head": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status),
        "status_sha256": hashlib.sha256(status.encode()).hexdigest(),
    }


def _tree_moved(before: dict, after: dict) -> bool:
    """Did the CODE move?  Git bookkeeping alone never counts."""
    return any(before.get(key) != after.get(key) for key in
               ("receiver_tree_sha256", "producer_identity", "arm_identity"))


def library_dir(row: CaptureRow) -> Path:
    return corpus.work_dir("feature-library", row.key)


def _sha_bytes(*chunks: bytes) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def _sha_array(values) -> bytes:
    array = np.ascontiguousarray(values)
    return hashlib.sha256(
        f"{array.dtype.str}|{array.shape}|".encode()
        + array.tobytes()).digest()


def _key(prefix: str, *parts: bytes) -> str:
    return prefix + _sha_bytes(*parts)[:48]


# ---------------------------------------------------------------------------
# the raster stand-ins
# ---------------------------------------------------------------------------


class NoRaster:
    """A lane raster that has no pixels and says so.

    ``collect_color_evidence`` probes one RGB pixel to decide whether the
    lane is colour at all; that single probe is served from the recorded
    dtype so the production branch is taken.  Every other pixel read
    raises — which is the proof that a library run opened no raster.
    """

    __slots__ = ("dpi", "shape", "_probe")

    def __init__(self, dpi: float, shape: tuple[int, int], dtype: str) -> None:
        self.dpi = float(dpi)
        self.shape = (int(shape[0]), int(shape[1]))
        self._probe = np.zeros((1, 1, 3), np.dtype(dtype))

    def crop_native(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        if (r0, r1, c0, c1) == (0, 1, 0, 1):
            return self._probe
        raise RuntimeError(
            "feature-library run touched the raster at "
            f"({r0},{r1},{c0},{c1}) — the library is incomplete")

    def crop_luma(self, *args: int) -> np.ndarray:
        raise RuntimeError("feature-library run asked for luma pixels")

    def contains(self, r0: int, r1: int, c0: int, c1: int) -> bool:
        return (0 <= r0 < r1 <= self.shape[0]
                and 0 <= c0 < c1 <= self.shape[1])


class StubNative:
    """Enough of a native raster to build the lane schedule, and no more."""

    __slots__ = ("dpi", "shape", "source_sha256")

    def __init__(self, dpi: float, shape: tuple[int, int], sha: str) -> None:
        self.dpi = float(dpi)
        self.shape = (int(shape[0]), int(shape[1]))
        self.source_sha256 = sha


# ---------------------------------------------------------------------------
# the recorded lane
# ---------------------------------------------------------------------------


@dataclass
class LaneRecord:
    """One lane's shadowed feature path plus the frontier it was cut on."""

    lane_id: str
    arrays: dict[str, np.ndarray] = field(default_factory=dict)
    small: dict[str, object] = field(default_factory=dict)
    prior_certificate_ids: tuple[str, ...] = ()
    minted_certificate_ids: tuple[str, ...] = ()
    raster_dpi: float = 0.0
    raster_shape: tuple[int, int] = (0, 0)
    raster_dtype: str = "uint8"

    def nbytes(self) -> int:
        return int(sum(value.nbytes for value in self.arrays.values()))


def _lane_paths(directory: Path, lane_id: str) -> tuple[Path, Path]:
    return (directory / f"{lane_id}.npz", directory / f"{lane_id}.pickle")


# ---------------------------------------------------------------------------
# the shims
# ---------------------------------------------------------------------------


class Shims:
    """Record or serve every raster-touching call the payload path makes.

    Six seams, all content-addressed on their own inputs:

    ``window_raw_crops``      the per-window native probe (its MAXIMUM is
                              the region divisor decision, and nothing
                              else about it survives the call);
    ``crop_features``         the A0 base features;
    ``_fit_registration``     the C/M/Y plane residuals;
    ``_features_with_page_fraction``   the A1 corrected features;
    ``place_committed``       the committed-geometry re-derivation;
    ``refine_color_address_once``      the R level's refinement.

    Recording keeps the real function and stores what it returned;
    serving never calls it.
    """

    def __init__(self, *, recording: bool) -> None:
        self.recording = recording
        self.current: LaneRecord | None = None
        self.shared: dict[str, object] = {}
        self._saved: list[tuple[object, str, object]] = []
        self.misses: list[str] = []
        # Recording only: the region's own real crops, alive exactly as
        # long as production keeps them.
        self._real_crops_by_patch: dict[int, tuple] = {}

    # -- storage -------------------------------------------------------
    def _put_array(self, key: str, value) -> None:
        assert self.current is not None
        self.current.arrays[key] = np.ascontiguousarray(value)

    def _get_array(self, key: str):
        assert self.current is not None
        try:
            return self.current.arrays[key]
        except KeyError:
            self.misses.append(key)
            raise SystemExit(
                f"feature library: no recorded array for {key} in lane "
                f"{self.current.lane_id} — the library does not cover this "
                "configuration (REFUSING; a library run never recomputes)"
            ) from None

    def _put_small(self, key: str, value: object, *, shared: bool = False
                   ) -> None:
        target = self.shared if shared else self.current.small  # type: ignore
        target[key] = value

    def _get_small(self, key: str, *, shared: bool = False):
        target = self.shared if shared else self.current.small  # type: ignore
        try:
            return target[key]
        except KeyError:
            self.misses.append(key)
            raise SystemExit(
                f"feature library: no recorded record for {key} — the "
                "library does not cover this configuration (REFUSING)"
            ) from None

    # -- the six seams -------------------------------------------------
    def install(self) -> None:
        from holo.receive import color_payload, place, production_color

        real_crops = color_payload.window_raw_crops
        real_features = color_payload.crop_features
        real_registration = color_payload._fit_registration
        real_corrected = color_payload._features_with_page_fraction
        real_place = place.place_committed
        real_refine = production_color.refine_color_address_once

        def crops(raster, patches, pitch_px):
            ids = tuple(int(row.patch_id) for row in patches)
            key = _key("m", repr((ids, float(pitch_px))).encode())
            if self.recording:
                out = real_crops(raster, patches, pitch_px)
                self._put_small(key, max(
                    (float(np.max(raw)) if raw.size else 0.0)
                    for _y0, _x0, raw in out.values()) if out else 0.0)
                self._real_crops_by_patch = out
                # The region loop's divisor probe must see the REAL
                # maxima; only the identity slot is rewritten so the
                # shimmed ``crop_features`` knows which window it has.
                return {patch_id: (patch_id, 0, value[2])
                        for patch_id, value in out.items()}
            probe = np.full((1, 1, 1), float(self._get_small(key)))
            # The tuple the region loop forwards to ``crop_features``
            # carries the patch identity, so the served pair is
            # self-consistent and the real crop never has to exist.
            return {int(row.patch_id): (int(row.patch_id), 0, probe)
                    for row in patches}

        def features(crop, scan_points_yx, pitch_px, divisor):
            patch_id = int(crop[0])
            key = _key(
                "b", repr((patch_id, float(pitch_px), float(divisor))).encode(),
                _sha_array(scan_points_yx))
            if self.recording:
                self._put_array(key, real_features(
                    self._real_crop(patch_id), scan_points_yx, pitch_px,
                    divisor))
            return self._get_array(key)

        def registration(raster, rows, base_features, spec):
            ids = tuple(int(row.patch.patch_id) for row in rows)
            key = _key("r", repr(ids).encode(),
                       *(_sha_array(value) for value in base_features))
            if self.recording:
                self._put_small(key, real_registration(
                    raster, rows, base_features, spec))
                # The region loop drops its crops immediately before this
                # call; drop the recorder's alias here too, so recording
                # never holds a region's raw crops longer than production
                # would have.
                self._real_crops_by_patch = {}
            return self._get_small(key)

        def corrected(raster, rows, residuals, spec, pitch_px, divisor):
            patch_id = int(rows.patch.patch_id)
            key = _key(
                "c",
                repr((patch_id, float(pitch_px), float(divisor),
                      tuple(repr(value) for value in residuals))).encode(),
                _sha_array(rows.scan_points_yx))
            if self.recording:
                value = real_corrected(
                    raster, rows, residuals, spec, pitch_px, divisor)
                self._put_small(key + "-none", value is None)
                if value is not None:
                    self._put_array(key, value)
            if self._get_small(key + "-none"):
                return None
            return self._get_array(key)

        def placed(raster, spec, *, poses, regions):
            key = _key(
                "p", repr((tuple(row.pose_id for row in poses),
                           tuple(row.region_id for row in regions))).encode())
            if self.recording:
                self._put_small(key, real_place(
                    raster, spec, poses=poses, regions=regions), shared=True)
            return self._get_small(key, shared=True)

        def refined(raster, address, budget, spec, certificates):
            key = _key(
                "x", repr((
                    tuple(int(row.patch_id)
                          for row in address.payload_placements),
                    tuple(row.certificate_id for row in certificates))
                ).encode())
            if self.recording:
                self._put_small(key, real_refine(
                    raster, address, budget, spec, certificates), shared=True)
            return self._get_small(key, shared=True)

        for module, name, replacement in (
                (color_payload, "window_raw_crops", crops),
                (color_payload, "crop_features", features),
                (color_payload, "_fit_registration", registration),
                (color_payload, "_features_with_page_fraction", corrected),
                (place, "place_committed", placed),
                (production_color, "place_committed", placed),
                (production_color, "refine_color_address_once", refined)):
            self._saved.append((module, name, getattr(module, name)))
            setattr(module, name, replacement)

    def _real_crop(self, patch_id: int) -> tuple:
        return self._real_crops_by_patch[patch_id]

    def remove(self) -> None:
        for module, name, original in reversed(self._saved):
            setattr(module, name, original)
        self._saved.clear()

    def __enter__(self) -> "Shims":
        self.install()
        return self

    def __exit__(self, *exc: object) -> None:
        self.remove()


class LaneHook:
    """Wrap the payload stage so every lane's frontier is exact.

    ``ProductionColorPayload.process`` is the one place that sees a
    lane's identity, its EXACT prior certificate frontier, and the
    certificates it mints.  Recording there needs no guesswork about
    barrier order, and serving there is where a diverged frontier is
    caught before a single stale feature is used.
    """

    def __init__(self, shims: Shims, directory: Path, *, recording: bool,
                 strict: bool = True) -> None:
        self.shims = shims
        self.directory = directory
        self.recording = recording
        self.strict = strict
        self.lanes: list[dict] = []
        self.divergence: dict | None = None
        self._saved = None

    def install(self) -> None:
        from holo.receive.production_color import ProductionColorPayload

        original = ProductionColorPayload.process
        self._saved = original
        hook = self

        def process(self, context, survey_product, address_product):
            return hook._around(
                original, self, context, survey_product, address_product)

        ProductionColorPayload.process = process

    def remove(self) -> None:
        from holo.receive.production_color import ProductionColorPayload

        if self._saved is not None:
            ProductionColorPayload.process = self._saved
            self._saved = None

    def __enter__(self) -> "LaneHook":
        self.install()
        return self

    def __exit__(self, *exc: object) -> None:
        self.remove()

    def _around(self, original, processor, context, survey, address):
        lane_id = context.lane.lane_id
        prior = tuple(row.certificate_id
                      for row in context.evidence.certificates)
        started = time.process_time()
        if self.recording:
            record = LaneRecord(
                lane_id=lane_id, prior_certificate_ids=prior,
                raster_dpi=float(context.raster.dpi),
                raster_shape=tuple(int(v) for v in context.raster.shape),
                raster_dtype=str(np.asarray(
                    context.raster.crop_native(0, 1, 0, 1)).dtype))
            self.shims.current = record
            output = original(processor, context, survey, address)
            record.minted_certificate_ids = tuple(
                row.certificate_id for row in output.product.certificates)
            self._write(record)
            self.lanes.append({
                "lane_id": lane_id,
                "prior_certificates": len(prior),
                "certificates": len(record.minted_certificate_ids),
                "arrays": len(record.arrays),
                "array_mib": round(record.nbytes() / 2**20, 1),
                "cpu_s": round(time.process_time() - started, 1),
            })
            self.shims.current = None
            return output
        record = self._read(lane_id)
        if tuple(record.prior_certificate_ids) != prior:
            recorded = set(record.prior_certificate_ids)
            live = set(prior)
            self.divergence = {
                "lane_id": lane_id,
                "recorded_prior": len(recorded),
                "live_prior": len(live),
                "missing": len(recorded - live),
                "extra": len(live - recorded),
            }
            message = (
                f"feature library: lane {lane_id}'s prior certificate "
                f"frontier diverged from the dump (recorded {len(recorded)}, "
                f"live {len(live)}: {len(recorded - live)} missing, "
                f"{len(live - recorded)} extra). Its recorded features were "
                "cut against a different KnownField, so they are STALE.")
            if self.strict:
                raise SystemExit(message + " REFUSING.")
            print("!! " + message, file=sys.stderr, flush=True)
        self.shims.current = record
        output = original(processor, context, survey, address)
        minted = tuple(row.certificate_id
                       for row in output.product.certificates)
        self.lanes.append({
            "lane_id": lane_id,
            "prior_certificates": len(prior),
            "certificates": len(minted),
            "recorded_certificates": len(record.minted_certificate_ids),
            "identical_to_dump": (
                set(minted) == set(record.minted_certificate_ids)),
            "cpu_s": round(time.process_time() - started, 1),
        })
        self.shims.current = None
        return output

    def _write(self, record: LaneRecord) -> None:
        npz_path, pickle_path = _lane_paths(self.directory, record.lane_id)
        np.savez_compressed(npz_path, **record.arrays)
        pickle_path.write_bytes(pickle.dumps({
            "small": record.small,
            "prior_certificate_ids": record.prior_certificate_ids,
            "minted_certificate_ids": record.minted_certificate_ids,
            "raster_dpi": record.raster_dpi,
            "raster_shape": record.raster_shape,
            "raster_dtype": record.raster_dtype,
        }, protocol=5))

    def _read(self, lane_id: str) -> LaneRecord:
        npz_path, pickle_path = _lane_paths(self.directory, lane_id)
        if not npz_path.is_file() or not pickle_path.is_file():
            raise SystemExit(
                f"feature library: lane {lane_id} is not in the library at "
                f"{self.directory} — REFUSING")
        blob = pickle.loads(pickle_path.read_bytes())
        with np.load(npz_path) as handle:
            arrays = {name: handle[name] for name in handle.files}
        return LaneRecord(
            lane_id=lane_id, arrays=arrays, small=blob["small"],
            prior_certificate_ids=tuple(blob["prior_certificate_ids"]),
            minted_certificate_ids=tuple(blob["minted_certificate_ids"]),
            raster_dpi=blob["raster_dpi"], raster_shape=blob["raster_shape"],
            raster_dtype=blob["raster_dtype"])


# ---------------------------------------------------------------------------
# the two commands
# ---------------------------------------------------------------------------


#: The run's explicit sweep record (PK-CLEAN), set once by ``main`` from
#: the CLI flags and threaded into ``replay_lanes``.  ``None`` = the
#: frozen constants the policy id names.  Only ``--force-null`` is still
#: an environment variable, because it is a contract that must reach code
#: paths no configuration object touches.
STACK_CONFIG = None


def _hatches() -> dict:
    """What moved the arms off their frozen constants, for the record."""
    rows: dict = {"HOLO_COLOR_STACK_FORCE_NULL":
                  os.environ.get("HOLO_COLOR_STACK_FORCE_NULL")}
    rows = {name: value for name, value in rows.items() if value}
    if STACK_CONFIG is not None:
        rows["stack_config"] = {
            "window_photometry_prior_labels":
                STACK_CONFIG.window_photometry.prior_labels,
            "head_saturation_floor": STACK_CONFIG.head_saturation_floor,
            "context": STACK_CONFIG.context.policy_token,
        }
    return rows


def _index_path(directory: Path) -> Path:
    return directory / "index.json"


def _prepare(row: CaptureRow, lanes: tuple[str, ...] | None,
             workers: int | None = None):
    if workers is not None:
        from holo.receive import _parallel

        _parallel.set_worker_count(workers)
    cache = state_cache.load(row, verbose=False)
    state_cache.verify_against_provenance(row, cache)
    spec = corpus.resolve_spec(row, cache.format_row_id)
    recorded = corpus.provenance_row(row.key)
    defer = recorded["baseline"]["flags"]["complete"]
    defer_close = True if defer == "unknown" else bool(defer)
    lane_filter = (None if lanes is None
                   else (lambda lane: lane.lane_id in lanes))
    return cache, spec, defer_close, lane_filter


def _report(row: CaptureRow, cache, spec, arm: str, mode: str,
            certificates, outcomes, hook: LaneHook, wall: float, cpu: float,
            extra: dict) -> dict:
    from holo.receive.color_payload import COLOR_PAYLOAD_POLICY_ID

    lane_by_certificate = {
        certificate.certificate_id: lane.lane_id
        for lane in outcomes for certificate in lane.certificates}
    counts: dict[str, int] = {}
    for record in certificates:
        counts[record.stream_id] = counts.get(record.stream_id, 0) + 1
    report = {
        # Deliberately the ab_runner schema: address_delta and gt_score
        # read these files unchanged.
        "schema": "color-uplift-run-1",
        "mode": mode,
        "arm": arm,
        "capture": row.key,
        "kind": row.kind,
        "engine": row.engine,
        "role": row.role,
        "force_null": bool(os.environ.get("HOLO_COLOR_STACK_FORCE_NULL")),
        "replay_is_development_signal": True,
        "library_tier_note": (
            "feature-library run: gates ITERATION only. A committed-pose "
            "replay gates a merge; a FULL decode gates a bar."),
        "worktree": {
            "head": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(_git("status", "--porcelain"))},
        "tree_state_after": tree_state(),
        "color_payload_policy_id": COLOR_PAYLOAD_POLICY_ID,
        "producer_identity": producer_identity(),
        "library_schema": LIBRARY_SCHEMA,
        "format_row_id": cache.format_row_id,
        "codec_id": spec.codec_id,
        "stream_ids": list(spec.stream_ids),
        "capture_sha256": cache.capture_sha256,
        "state_sha256": cache.state_sha256,
        "provenance_verified": True,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "hatches": _hatches()},
        "totals": {
            "certificates": len(certificates),
            "by_stream": dict(sorted(counts.items())),
            "wall_s": round(wall, 1),
            "cpu_s": round(cpu, 1),
            "peak_rss_mib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20),
        },
        "archived": {
            "certificates": cache.n_state_certificates,
            "certificate_ids": sorted(cache.certificates_by_id),
            "certificates_by_lane": {
                level.lane_id: len(level.certificate_ids)
                for level in cache.levels}},
        "library_lanes": hook.lanes,
        "frontier_divergence": hook.divergence,
        "lanes": [
            {
                "ordinal": lane.ordinal,
                "lane_id": lane.lane_id,
                "lane_kind": lane.lane_kind,
                "evidence_lane_id": lane.evidence_lane_id,
                "placements": lane.placements,
                "label_placements": lane.label_placements,
                "prior_certificates": lane.prior_certificates,
                "blocks": lane.blocks,
                "attempts": lane.attempts,
                "certificates": len(lane.certificates),
                "certificates_by_stream": {},
                # PK4.3's u-lanes have NO archived level (the archived
                # decode never scheduled one), so their archived count is
                # null, not zero — ``ab_runner`` says the same thing the
                # same way, and reading past the end of the archived level
                # list crashed this reporter on the first library dump of
                # a u-lane-bearing plan (PK5).
                "archived_certificates": (
                    len(cache.levels[lane.ordinal].certificate_ids)
                    if lane.ordinal < len(cache.levels) else None),
                "wall_s": round(lane.wall_s, 1),
                "cpu_s": round(lane.cpu_s, 1),
                "build_address_s": round(lane.build_address_s, 2),
                "details": lane.details,
            }
            for lane in outcomes],
        "certificates": [
            {
                "certificate_id": record.certificate_id,
                "page": int(record.page),
                "tile_yx": [int(record.tile_yx[0]), int(record.tile_yx[1])],
                "stream_id": record.stream_id,
                "lane_id": lane_by_certificate.get(record.certificate_id),
                "packed_user_bits_hex": record.packed_user_bits.hex(),
            }
            for record in certificates],
    }
    report.update(extra)
    return report


def cmd_dump(args: argparse.Namespace) -> int:
    """Record one replay's feature path into a reusable library."""
    from holo.receive.observer import ProvisionalReceiverWarning
    from holo.receive.scan import open_capture

    row = corpus.capture(args.capture)
    lanes = tuple(args.lane) if args.lane else None
    cache, spec, defer_close, lane_filter = _prepare(
        row, lanes, args.workers)
    directory = library_dir(row)
    native = open_capture(str(row.tiff_path()), row.scan_dpi)
    if native.source_sha256 != cache.capture_sha256:
        raise SystemExit(f"{row.key}: capture sha differs — REFUSING")
    shims = Shims(recording=True)
    hook = LaneHook(shims, directory, recording=True)
    tree_before = tree_state()
    started = time.perf_counter()
    cpu_started = time.process_time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        with shims, hook:
            outcomes, certificates = replay_lanes(
                cache, spec, native, defer_fountain_close=defer_close,
                lane_filter=lane_filter, stack_config=STACK_CONFIG,
                progress=lambda text: print(
                    f"    {text}", file=sys.stderr, flush=True))
    wall = time.perf_counter() - started
    cpu = time.process_time() - cpu_started
    (directory / "shared.pickle").write_bytes(
        pickle.dumps(shims.shared, protocol=5))
    index = {
        "schema": LIBRARY_SCHEMA,
        "capture": row.key,
        "capture_sha256": cache.capture_sha256,
        "state_sha256": cache.state_sha256,
        "format_row_id": cache.format_row_id,
        "producer_identity": producer_identity(),
        "producer_modules": list(PRODUCER_MODULES),
        "dump_hatches": _hatches(),
        "dump_arm": args.arm,
        "dump_head": _git("rev-parse", "HEAD"),
        "tree_state_before": tree_before,
        "tree_state_after": tree_state(),
        "dump_wall_s": round(wall, 1),
        "dump_cpu_s": round(cpu, 1),
        "lanes": hook.lanes,
        "lane_ids": [lane["lane_id"] for lane in hook.lanes],
        "shared_records": len(shims.shared),
        "bytes": {
            path.name: path.stat().st_size
            for path in sorted(directory.iterdir()) if path.is_file()},
    }
    index["total_bytes"] = sum(index["bytes"].values())
    index["tree_stable"] = not _tree_moved(
        index["tree_state_before"], index["tree_state_after"])
    if not index["tree_stable"]:
        print("!! THE TREE MOVED DURING THIS DUMP — the library is VOID, "
              "delete it and re-dump", file=sys.stderr, flush=True)
    _index_path(directory).write_text(
        json.dumps(index, indent=1, sort_keys=True) + "\n")
    report = _report(row, cache, spec, args.arm, "library-dump",
                     certificates, outcomes, hook, wall, cpu,
                     {"library_index": str(_index_path(directory))})
    out = Path(args.out) if args.out else (
        corpus.work_dir("runs") / f"{row.key}-libdump-{args.arm}.json")
    out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "capture": row.key, "mode": "library-dump",
        "certificates": len(certificates),
        "library_mib": round(index["total_bytes"] / 2**20, 1),
        "wall_s": round(wall, 1), "cpu_s": round(cpu, 1),
        "library": str(directory), "out": str(out)}))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Execute the stack from the library, with no raster at all."""
    from holo.receive import cascade
    from holo.receive.observer import ProvisionalReceiverWarning

    row = corpus.capture(args.capture)
    lanes = tuple(args.lane) if args.lane else None
    cache, spec, defer_close, lane_filter = _prepare(
        row, lanes, args.workers)
    directory = library_dir(row)
    index_path = _index_path(directory)
    if not index_path.is_file():
        raise SystemExit(f"no feature library at {directory} — run `dump`")
    index = json.loads(index_path.read_text())
    for label, live, recorded in (
            ("library schema", LIBRARY_SCHEMA, index.get("schema")),
            ("capture sha", cache.capture_sha256, index.get("capture_sha256")),
            ("state sha", cache.state_sha256, index.get("state_sha256")),
            ("producer identity", producer_identity(),
             index.get("producer_identity"))):
        if live != recorded:
            raise SystemExit(
                f"feature library: {label} moved (live {str(live)[:24]}… != "
                f"library {str(recorded)[:24]}…) — REFUSING to run")
    if index.get("tree_stable") is False:
        raise SystemExit(
            "feature library: its DUMP ran while the tree was moving — the "
            "library is void; delete it and re-dump. REFUSING to run")
    tree_before = tree_state()
    shims = Shims(recording=False)
    shims.shared = pickle.loads((directory / "shared.pickle").read_bytes())
    hook = LaneHook(shims, directory, recording=False,
                    strict=not args.allow_stale_frontier)
    # Per-lane raster facts, recorded by the dump; the stub serves the
    # single RGB probe and refuses every other pixel read.
    facts = {}
    for lane_id in index["lane_ids"]:
        _npz, pickle_path = _lane_paths(directory, lane_id)
        blob = pickle.loads(pickle_path.read_bytes())
        facts[lane_id] = (blob["raster_dpi"], blob["raster_shape"],
                          blob["raster_dtype"])
    by_label: dict[str, tuple] = {}
    for lane in cache.plan:
        if lane.lane_id in facts:
            by_label[lane.base_lane_id] = facts[lane.lane_id]

    saved = (cascade._materialize, cascade.release_derived_lanes)

    def materialize(context, level, *, defer_pixels: bool = False):
        try:
            dpi, shape, dtype = by_label[level.label]
        except KeyError:
            raise SystemExit(
                f"feature library: no recorded raster facts for level "
                f"{level.label} — REFUSING") from None
        return NoRaster(dpi, shape, dtype)

    cascade._materialize = materialize
    cascade.release_derived_lanes = lambda native: None
    native = StubNative(row.scan_dpi, cache.capture_shape_yx,
                        cache.capture_sha256)
    started = time.perf_counter()
    cpu_started = time.process_time()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ProvisionalReceiverWarning)
            with shims, hook:
                outcomes, certificates = replay_lanes(
                    cache, spec, native, defer_fountain_close=defer_close,
                    lane_filter=lane_filter, stack_config=STACK_CONFIG,
                    seed_archived_certificates=bool(
                        args.seed_archived_certificates),
                    progress=lambda text: print(
                        f"    {text}", file=sys.stderr, flush=True))
    finally:
        cascade._materialize, cascade.release_derived_lanes = saved
    wall = time.perf_counter() - started
    cpu = time.process_time() - cpu_started
    report = _report(row, cache, spec, args.arm, "library", certificates,
                     outcomes, hook, wall, cpu, {
                         "library_index": str(index_path),
                         "dump_hatches": index["dump_hatches"],
                         "dump_wall_s": index["dump_wall_s"],
                         "dump_cpu_s": index["dump_cpu_s"],
                         "library_mib": round(
                             index["total_bytes"] / 2**20, 1),
                         "raster_opened": False,
                         "seed_archived_certificates": bool(
                             args.seed_archived_certificates),
                         **({"kill_test": (
                             "PRIORS SEEDED WITH THE ARCHIVED FINAL "
                             "FRONTIER: maximal conditioning, structurally "
                             "unreachable in deployment. A null result "
                             "kills the packet; a positive one measures "
                             "NOTHING.")} if args.seed_archived_certificates
                            else {}),
                         "tree_state_before": tree_before,
                         "dump_tree_state": index.get("tree_state_before"),
                         "arm_identity": tree_before["arm_identity"],
                         "dump_arm_identity": (
                             index.get("tree_state_before") or {}).get(
                                 "arm_identity"),
                         "tree_matches_dump": (
                             tree_before.get("arm_identity")
                             == (index.get("tree_state_before")
                                 or {}).get("arm_identity")),
                     })
    out = Path(args.out) if args.out else (
        corpus.work_dir("runs") / f"{row.key}-library-{args.arm}.json")
    out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    if _tree_moved(tree_before, tree_state()):
        print("!! THE TREE MOVED DURING THIS RUN — the result is VOID",
              file=sys.stderr, flush=True)
    if not report["tree_matches_dump"]:
        print("!! this run's ARM code differs from the DUMP's; the feature "
              "path is identical (producer identity checked) but a "
              "cert-set delta is then arm-vs-arm, not library-vs-replay",
              file=sys.stderr, flush=True)
    identical = [lane for lane in hook.lanes
                 if lane.get("identical_to_dump") is False]
    print(json.dumps({
        "capture": row.key, "mode": "library", "arm": args.arm,
        "certificates": len(certificates),
        "by_stream": report["totals"]["by_stream"],
        "lanes_differing_from_dump": [lane["lane_id"] for lane in identical],
        "frontier_divergence": hook.divergence,
        "wall_s": round(wall, 1), "cpu_s": round(cpu, 1),
        "dump_wall_s": index["dump_wall_s"], "dump_cpu_s": index["dump_cpu_s"],
        "out": str(out)}))
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    row = corpus.capture(args.capture)
    directory = library_dir(row)
    path = _index_path(directory)
    if not path.is_file():
        print(json.dumps({"capture": row.key, "library": None}))
        return 1
    index = json.loads(path.read_text())
    print(json.dumps({
        "capture": row.key,
        "library": str(directory),
        "lanes": index["lane_ids"],
        "total_mib": round(index["total_bytes"] / 2**20, 1),
        "dump_wall_s": index["dump_wall_s"],
        "dump_cpu_s": index["dump_cpu_s"],
        "producer_identity_matches":
            index["producer_identity"] == producer_identity(),
        "dump_hatches": index["dump_hatches"]}, indent=1))
    return 0


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--capture", required=True)
    parser.add_argument("--arm", default="library")
    parser.add_argument("--lane", action="append", default=[])
    parser.add_argument("--out", default=None)
    parser.add_argument("--force-null", action="store_true")
    parser.add_argument("--window-phot", default=None, metavar="PRIOR",
                        help="A3's shrinkage prior, off its frozen 20 "
                             "(the two retired dispersion floors are no "
                             "longer accepted — MEASUREMENTS §12)")
    parser.add_argument("--head-satfloor", default=None, metavar="FRACTION")
    parser.add_argument("--ctx", default=None,
                        help="A5 variant: matrix|off[:floors] (the "
                             "per-plane K port is RETIRED, §11.4/§12)")
    parser.add_argument("--workers", type=int, default=None,
                        help="pooled-kernel worker count (execution-only; "
                             "the `confetti.py decode --workers` seam)")


def _sweep_config(args):
    """The sweep flags as ONE explicit ``StackConfig``, or ``None``."""
    from .ab_runner import _stack_config

    return _stack_config(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.feature_library", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    item = sub.add_parser("dump")
    _common(item)
    item.set_defaults(handler=cmd_dump)

    item = sub.add_parser("run")
    _common(item)
    item.add_argument("--allow-stale-frontier", action="store_true",
                      help="continue past a diverged prior-certificate "
                           "frontier (the features are STALE from that lane "
                           "on; the run says so in its JSON)")
    item.add_argument("--seed-archived-certificates", action="store_true",
                      help="THE KILL TEST (PK10): hand every lane the "
                           "archived FINAL certificate frontier as priors. "
                           "The frontier check will diverge by "
                           "construction, so pass --allow-stale-frontier "
                           "with it and read the lane report: the shimmed "
                           "seams are keyed on placements and features, "
                           "not on certificates, so a lane whose window "
                           "inventory the seeds do not change is served "
                           "EXACTLY (a miss is a hard refusal, never a "
                           "silent recomputation).")
    item.set_defaults(handler=cmd_run)

    item = sub.add_parser("info")
    item.add_argument("--capture", required=True)
    item.set_defaults(handler=cmd_info)

    args = parser.parse_args(argv)
    if getattr(args, "force_null", False):
        os.environ["HOLO_COLOR_STACK_FORCE_NULL"] = "1"
    global STACK_CONFIG
    STACK_CONFIG = _sweep_config(args)
    return int(args.handler(args))


if __name__ == "__main__":
    from _color_uplift_harness import feature_library as _module

    raise SystemExit(_module.main())
