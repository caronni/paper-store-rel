"""Read-only extraction of the archived states' committed geometry.

The corpus states are 8 MB … 1.7 GB; parsing one costs seconds to
minutes and the harness needs the same handful of typed records on every
replay.  This module reads a state ONCE (``load_session(...,
defer_fountain_validation=True)`` — legal across policy bumps, the policy
check lives only in ``run_receive``) and caches exactly the committed
facts a payload replay consumes:

* the capture facts and its exact scale plan;
* per level: the survey/address/payload artifacts (certificate ids,
  quarantined patch ids);
* per lane: the durable ``SurveyRegionRecord`` and ``PoseRecord`` rows;
* every ``TileCertificateRecord``.

Durable evidence blocks are deliberately NOT cached: a replay re-derives
its own blocks, and they are the bulk of the file.

The cache lives under ``<work>/cache/<capture>/`` and is keyed by the
state's SHA-256 plus this module's ``CACHE_VERSION`` — a re-decoded or
edited state can never be silently reused.  Nothing is written next to
the archived state.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.state_cache build --capture xerox-c3-cmy7
"""
from __future__ import annotations

import argparse
import json
import pickle
import time
from dataclasses import dataclass
from pathlib import Path

from . import corpus
from .corpus import CaptureRow

CACHE_VERSION = 3


@dataclass(frozen=True, slots=True)
class LevelFacts:
    """One archived barrier's committed identities."""

    ordinal: int
    lane_id: str
    survey_id: str | None
    address_id: str | None
    payload_id: str | None
    certificate_ids: tuple[str, ...]
    quarantined_patch_ids: tuple[int, ...]
    pose_ids: tuple[str, ...]
    n_blocks: int
    n_attempts: int


@dataclass(frozen=True, slots=True)
class CaptureCache:
    """Everything a payload replay needs from one archived state."""

    key: str
    state_sha256: str
    format_row_id: str
    page_hypotheses: tuple[int, ...] | None
    close_status: str
    capture_sha256: str
    capture_dpi: float
    capture_dtype: str
    capture_shape_yx: tuple[int, int]
    capture_channels: int
    plan: tuple
    levels: tuple[LevelFacts, ...]
    regions_by_lane: dict[str, tuple]
    poses_by_lane: dict[str, tuple]
    certificates_by_id: dict[str, object]
    n_state_certificates: int

    def lane(self, ordinal: int):
        return self.plan[ordinal]

    def certificates_before(self, ordinal: int) -> tuple:
        """The prior-barrier certificate frontier for one level.

        A certificate minted at level N conditions and suppresses only
        from level N+1 (RECEIVE-DESIGN §6.2 prior-barrier law); this is
        the exact set the archived lane saw.
        """
        rows = []
        for level in self.levels[:ordinal]:
            rows.extend(self.certificates_by_id[identity]
                        for identity in level.certificate_ids)
        return tuple(rows)

    def certificates_at(self, ordinal: int) -> tuple:
        level = self.levels[ordinal]
        return tuple(self.certificates_by_id[identity]
                     for identity in level.certificate_ids)


def cache_dir(row: CaptureRow) -> Path:
    return corpus.work_dir("cache", row.key)


def _manifest_path(row: CaptureRow) -> Path:
    return cache_dir(row) / "cache.json"


def _pickle_path(row: CaptureRow) -> Path:
    return cache_dir(row) / "committed.pickle"


def build(row: CaptureRow, *, state_sha256: str | None = None,
          verbose: bool = True) -> CaptureCache:
    """Parse one archived state read-only and materialise its cache."""
    from holo.receive.session import load_session

    state_path = row.state_path()
    started = time.perf_counter()
    sha = state_sha256 or corpus.sha256_file(state_path)
    state = load_session(state_path, defer_fountain_validation=True)
    if len(state.captures) != 1:
        raise SystemExit(
            f"{row.key}: expected a single-capture state, found "
            f"{len(state.captures)} (the replay's barrier order is only "
            "well-defined for one capture)")
    record = state.captures[0]
    levels: list[LevelFacts] = []
    for ordinal, level in enumerate(record.levels):
        address = level.address
        payload = level.payload
        levels.append(LevelFacts(
            ordinal=ordinal,
            lane_id=record.plan[ordinal].lane_id,
            survey_id=None if level.survey is None else level.survey.survey_id,
            address_id=None if address is None else address.address_id,
            payload_id=None if payload is None else payload.payload_id,
            certificate_ids=(() if payload is None
                             else tuple(payload.certificate_ids)),
            quarantined_patch_ids=(() if address is None else tuple(
                address.quarantined_patch_ids)),
            pose_ids=() if address is None else tuple(address.pose_ids),
            n_blocks=0 if payload is None else int(payload.n_blocks),
            n_attempts=0 if payload is None else int(payload.n_attempts),
        ))
    regions: dict[str, list] = {}
    for region in state.regions:
        regions.setdefault(region.lane_id, []).append(region)
    poses: dict[str, list] = {}
    for pose in state.poses:
        poses.setdefault(pose.lane_id, []).append(pose)
    cache = CaptureCache(
        key=row.key,
        state_sha256=sha,
        format_row_id=state.format_row_id,
        page_hypotheses=state.page_hypotheses,
        close_status=state.close.status.value,
        capture_sha256=record.source_sha256,
        capture_dpi=float(record.dpi),
        capture_dtype=str(record.dtype),
        capture_shape_yx=tuple(int(value) for value in record.shape_yx),
        capture_channels=int(record.channels),
        plan=tuple(record.plan),
        levels=tuple(levels),
        regions_by_lane={key: tuple(value) for key, value in regions.items()},
        poses_by_lane={key: tuple(value) for key, value in poses.items()},
        certificates_by_id={
            row_.certificate_id: row_ for row_ in state.certificates},
        n_state_certificates=len(state.certificates),
    )
    if abs(cache.capture_dpi - row.scan_dpi) > 1e-6:
        raise SystemExit(
            f"{row.key}: archived capture dpi {cache.capture_dpi} disagrees "
            f"with the registry's {row.scan_dpi}")
    directory = cache_dir(row)
    _pickle_path(row).write_bytes(pickle.dumps(cache, protocol=5))
    _manifest_path(row).write_text(json.dumps({
        "schema": "color-uplift-state-cache",
        "cache_version": CACHE_VERSION,
        "capture": row.key,
        "state_path": str(state_path),
        "state_sha256": sha,
        "state_bytes": state_path.stat().st_size,
        "format_row_id": cache.format_row_id,
        "capture_sha256": cache.capture_sha256,
        "capture_dpi": cache.capture_dpi,
        "capture_shape_yx": list(cache.capture_shape_yx),
        "capture_channels": cache.capture_channels,
        "page_hypotheses": (None if cache.page_hypotheses is None
                            else list(cache.page_hypotheses)),
        "close_status": cache.close_status,
        "levels": len(cache.levels),
        "plan_lanes": [lane.lane_id for lane in cache.plan],
        "certificates": cache.n_state_certificates,
        "certificates_by_level": {
            level.lane_id: len(level.certificate_ids)
            for level in cache.levels},
        "poses_by_lane": {key: len(value)
                          for key, value in cache.poses_by_lane.items()},
        "regions_by_lane": {key: len(value)
                            for key, value in cache.regions_by_lane.items()},
        "build_seconds": round(time.perf_counter() - started, 1),
    }, indent=1, sort_keys=True) + "\n")
    if verbose:
        print(f"{row.key}: cached {cache.n_state_certificates} certificates, "
              f"{len(cache.levels)} levels in "
              f"{time.perf_counter() - started:.1f}s -> {directory}")
    return cache


def load(row: CaptureRow, *, rebuild: bool = False,
         verbose: bool = True) -> CaptureCache:
    """Load the cache, rebuilding when the state SHA or version moved."""
    manifest_path = _manifest_path(row)
    sha = corpus.sha256_file(row.state_path())
    if not rebuild and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        if (manifest.get("cache_version") == CACHE_VERSION
                and manifest.get("state_sha256") == sha
                and _pickle_path(row).is_file()):
            cache = pickle.loads(_pickle_path(row).read_bytes())
            if not isinstance(cache, CaptureCache):
                raise SystemExit(f"{row.key}: corrupt cache payload")
            return cache
    return build(row, state_sha256=sha, verbose=verbose)


def verify_against_provenance(row: CaptureRow, cache: CaptureCache) -> None:
    """Refuse to run on any artifact the campaign did not freeze."""
    recorded = corpus.provenance_row(row.key)
    expected_state = recorded["artifacts"]["state"]["sha256"]
    if cache.state_sha256 != expected_state:
        raise SystemExit(
            f"{row.key}: state sha {cache.state_sha256[:16]}… != "
            f"provenance {expected_state[:16]}… — REFUSING to run")
    if cache.format_row_id != recorded["format_row_id"]:
        raise SystemExit(
            f"{row.key}: state format {cache.format_row_id} != provenance "
            f"{recorded['format_row_id']} — REFUSING to run")


def cmd_build(args: argparse.Namespace) -> int:
    keys = args.capture or [row.key for row in corpus.CAPTURES]
    for key in keys:
        row = corpus.capture(key)
        cache = load(row, rebuild=args.rebuild)
        print(json.dumps({
            "capture": key,
            "certificates": cache.n_state_certificates,
            "levels": len(cache.levels),
            "lanes_with_poses": sorted(cache.poses_by_lane),
            "close": cache.close_status,
        }))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.state_cache", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    item = sub.add_parser("build")
    item.add_argument("--capture", action="append", default=[])
    item.add_argument("--rebuild", action="store_true")
    item.set_defaults(handler=cmd_build)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    # Re-enter through the package so pickled records carry their real
    # module path (``python -m`` would otherwise name them __main__).
    from _color_uplift_harness import state_cache as _module

    raise SystemExit(_module.main())
